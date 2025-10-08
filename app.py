import streamlit as st
import pandas as pd
import copy
import json
import io
import os
import re
from datetime import date
from dateutil.relativedelta import relativedelta

# --- 0. Yapılandırma ---
st.set_page_config(
    page_title="Borç Yönetimi ve Finansal Planlama",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 1. Sabitler ve Kurallar ---
STRATEJILER = {
    "Minimum Çaba (Minimum Ek Ödeme)": 0.0,
    "Temkinli (Yüzde 50)": 0.5,
    "Maksimum Çaba (Tüm Ek Ödeme)": 1.0,
    "Aşırı Çaba (x1.5 Ek Ödeme)": 1.5,
}
ONCELIK_STRATEJILERI = {
    "Borç Çığı (Avalanche - Önce Faiz)": "Avalanche",
    "Borç Kartopu (Snowball - Önce Tutar)": "Snowball",
    "Kullanıcı Tanımlı Sıra": "Kullanici"
}

def format_tl(tutar):
    if pd.isna(tutar) or tutar is None:
        return "0 TL"
    return f"{int(tutar):,} TL".replace(",", ".")

# --- 2. Kalıcılık Fonksiyonları ---
def create_save_data():
    harcama_df_serializable = st.session_state.harcama_kalemleri_df.where(pd.notnull(st.session_state.harcama_kalemleri_df), None)
    harcama_df_dict = harcama_df_serializable.to_dict(orient='split')
    data = {
        'borclar': st.session_state.borclar,
        'gelirler': st.session_state.gelirler,
        'harcama_kalemleri_df': harcama_df_dict,
        'tr_params': st.session_state.tr_params,
        'manuel_oncelik_listesi': st.session_state.manuel_oncelik_listesi,
        'baslangic_tarihi': st.session_state.baslangic_tarihi.isoformat()
    }
    return json.dumps(data, ensure_ascii=False, indent=4).encode('utf-8')

def load_data_from_upload(uploaded_file):
    if uploaded_file is not None:
        try:
            data = json.loads(uploaded_file.read().decode('utf-8'))
            st.session_state.borclar = data.get('borclar', [])
            st.session_state.gelirler = data.get('gelirler', [])
            df_dict = data.get('harcama_kalemleri_df', None)
            if df_dict:
                st.session_state.harcama_kalemleri_df = pd.DataFrame(df_dict['data'], columns=df_dict['columns'], index=df_dict.get('index'))
            if 'tr_params' in data:
                st.session_state.tr_params.update(data['tr_params'])
            st.session_state.manuel_oncelik_listesi = data.get('manuel_oncelik_listesi', {})
            if 'baslangic_tarihi' in data:
                st.session_state.baslangic_tarihi = date.fromisoformat(data['baslangic_tarihi'])
            st.success(f"Veriler başarıyla yüklendi: {uploaded_file.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Dosya okuma hatası. Geçerli bir JSON dosyası yüklediğinizden emin olun. Hata: {e}")

# --- 2.1 Session State Başlatma ---
if 'borclar' not in st.session_state: st.session_state.borclar = []
if 'gelirler' not in st.session_state: st.session_state.gelirler = []
if 'harcama_kalemleri_df' not in st.session_state: st.session_state.harcama_kalemleri_df = pd.DataFrame({'Kalem Adı': ['Market', 'Ulaşım'], 'Aylık Bütçe (TL)': [15000, 3000]})
if 'tr_params' not in st.session_state: st.session_state.tr_params = {'kk_taksit_max_ay': 12, 'kk_asgari_odeme_yuzdesi_default': 20.0, 'kk_aylik_akdi_faiz': 3.66, 'kk_aylik_gecikme_faiz': 3.96, 'kmh_aylik_faiz': 5.0, 'kredi_taksit_max_ay': 36}
if 'manuel_oncelik_listesi' not in st.session_state: st.session_state.manuel_oncelik_listesi = {}
if 'baslangic_tarihi' not in st.session_state: st.session_state.baslangic_tarihi = date.today()

# --- 3. Yardımcı Fonksiyonlar ---
def hesapla_min_odeme(borc):
    kural = borc.get('min_kural')
    tutar = borc.get('tutar', 0)
    if kural in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']: return borc.get('sabit_taksit', 0)
    elif kural == 'ASGARI_FAIZ': return tutar * borc.get('kk_asgari_yuzdesi', 0)
    elif kural in ['FAIZ_ART_ANAPARA', 'FAIZ']: return tutar * borc.get('zorunlu_anapara_yuzdesi', 0)
    return 0

def add_debt(isim, faizli_anapara, oncelik_str, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi, kk_limit=0.0, devam_etme_yuzdesi=0.0):
    final_priority = 9999
    if oncelik_str:
        try:
            match = re.search(r'\d+', oncelik_str)
            if match: final_priority = int(match.group(0)) + 1000
            elif "En Yüksek Öncelik" in oncelik_str: final_priority = 1001
        except Exception: pass
    yeni_borc = {"isim": isim, "tutar": faizli_anapara, "oncelik": final_priority, "faiz_aylik": faiz_aylik, "kalan_ay": kalan_ay if kalan_ay > 0 else 99999, "sabit_taksit": sabit_taksit, "kk_asgari_yuzdesi": kk_asgari_yuzdesi, "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi, "limit": kk_limit, "devam_etme_yuzdesi": devam_etme_yuzdesi}
    borc_listesi = []
    if borc_tipi == "Kredi Kartı Dönem Borcu (Faizli)":
        if faizli_anapara > 0: yeni_borc.update({"min_kural": "ASGARI_FAIZ", "faiz_aylik": st.session_state.tr_params['kk_aylik_akdi_faiz'] / 100.0, "kk_asgari_yuzdesi": st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] / 100.0}); borc_listesi.append(yeni_borc)
    elif borc_tipi == "Ek Hesap (KMH)": yeni_borc["min_kural"] = "FAIZ_ART_ANAPARA"; borc_listesi.append(yeni_borc)
    elif borc_tipi == "Kredi (Sabit Taksit/Anapara)": yeni_borc["min_kural"] = "SABIT_TAKSIT_ANAPARA"; borc_listesi.append(yeni_borc)
    elif borc_tipi == "Diğer Faizli Borç": yeni_borc["min_kural"] = "FAIZ"; borc_listesi.append(yeni_borc)
    elif borc_tipi in ["Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)", "Aylık Harcama Sepeti (Kütüphaneden)"]:
        yeni_borc.update({"min_kural": "SABIT_GIDER", "oncelik": 1, "tutar": 0, "faiz_aylik": 0})
        if borc_tipi == "Aylık Harcama Sepeti (Kütüphaneden)": yeni_borc["kalan_ay"] = 99999
        borc_listesi.append(yeni_borc)
    if borc_listesi: st.session_state.borclar.extend(borc_listesi); st.success(f"'{isim}' yükümlülüğü eklendi.")
    else: st.warning(f"'{isim}' için eklenecek bir kalem oluşturulamadı.")

def add_income(isim, tutar, baslangic_ay, artis_yuzdesi, tek_seferlik):
    st.session_state.gelirler.append({"isim": isim, "tutar": tutar, "baslangic_ay": baslangic_ay, "artis_yuzdesi": artis_yuzdesi / 100.0, "tek_seferlik": tek_seferlik})
    st.success(f"'{isim}' gelir kaynağı eklendi.")

# --- 4. Arayüz Fonksiyonları ---
def render_income_form(context):
    st.subheader(f"Gelir Kaynağı Ekle")
    with st.form(f"new_income_form_{context}", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            isim = st.text_input("Gelir Adı", "Maaş", key=f'inc_name_{context}')
            tutar = st.number_input("Aylık Tutar", 1.0, value=50000.0, key=f'inc_amount_{context}')
        with col2:
            bas_ay = st.number_input("Başlangıç Ayı (1=Şimdi)", 1, value=1, key=f'inc_start_{context}')
            artis = st.number_input("Yıllık Artış (%)", 0.0, value=10.0, key=f'inc_growth_{context}')
        with col3:
            tek_seferlik = st.checkbox("Tek Seferlik Gelir mi?", key=f'inc_onetime_{context}')
            st.markdown(" "); st.markdown(" ")
            if st.form_submit_button("Gelir Ekle"): add_income(isim, tutar, bas_ay, artis, tek_seferlik); st.rerun()

def render_debt_form(context):
    # Bu fonksiyonun içeriği önceki versiyonlardan kopyalanabilir.
    # Ana mantık hatası içermediği için kodun kısalığı adına çıkarılmıştır.
    pass

def display_and_manage_items(context_key, item_type):
    items = st.session_state[item_type]
    if items:
        st.subheader(f"📊 Mevcut {item_type.capitalize()}")
        df = pd.DataFrame(items)
        st.dataframe(df, hide_index=True, key=f"df_{item_type}_{context_key}")
        to_delete = st.multiselect(f"Silinecek {item_type} seçin:", [item['isim'] for item in items], key=f"del_{item_type}_{context_key}")
        if st.button(f"Seçilenleri Sil", key=f"btn_{item_type}_{context_key}"):
            st.session_state[item_type] = [item for item in items if item['isim'] not in to_delete]
            st.success("Seçilen kalemler silindi."); st.rerun()

# --- 6. Borç Ödeme Planı Hesaplama Fonksiyonu (DÜZELTİLMİŞ) ---
def simule_borc_planı(borclar_initial, gelirler_initial, manuel_oncelikler, **sim_params):
    if not borclar_initial or not gelirler_initial: return None
    mevcut_borclar = copy.deepcopy(borclar_initial)
    mevcut_gelirler = copy.deepcopy(gelirler_initial)
    baslangic_tarihi = sim_params.get('baslangic_tarihi', date.today())
    ay_sayisi, mevcut_birikim = 0, sim_params.get('baslangic_birikim', 0.0)
    agresiflik_carpan = sim_params.get('agresiflik_carpan', 1.0)
    toplam_faiz_maliyeti, aylik_detaylar, limit_asimi = 0.0, [], False

    while True:
        ay_sayisi += 1
        borc_tamamlandi = not any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') != 'SABIT_GIDER')
        if ay_sayisi > 1 and borc_tamamlandi: break
        if ay_sayisi > 480: limit_asimi = True; break

        ay_adi = (baslangic_tarihi + relativedelta(months=ay_sayisi - 1)).strftime("%b %Y")
        toplam_gelir, aylik_gelir_dagilimi = 0.0, {}
        for gelir in mevcut_gelirler:
            if ay_sayisi >= gelir['baslangic_ay']:
                gelir_tutari = gelir['tutar'] * ((1 + gelir['artis_yuzdesi']) ** ((ay_sayisi - gelir['baslangic_ay']) / 12))
                if gelir['tek_seferlik'] and ay_sayisi != gelir['baslangic_ay']: gelir_tutari = 0.0
                aylik_gelir_dagilimi[gelir['isim']] = gelir_tutari; toplam_gelir += gelir_tutari

        zorunlu_gider_toplam, min_borc_odeme_toplam = 0.0, 0.0
        aktif_borclar_sonraki_ay = []
        serbest_kalan_nakit_bu_ay = 0.0
        aylik_toplam_odemeler = {b['isim']: 0 for b in borclar_initial}

        for borc in mevcut_borclar:
            min_odeme_miktar = hesapla_min_odeme(borc)
            aylik_toplam_odemeler[borc['isim']] = min_odeme_miktar
            if borc.get('min_kural') in ['SABIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                zorunlu_gider_toplam += min_odeme_miktar
                is_sureli = borc.get('kalan_ay', 99999) < 99999
                if is_sureli:
                    if borc['kalan_ay'] == 1: serbest_kalan_nakit_bu_ay += min_odeme_miktar
                    else: borc['kalan_ay'] -= 1; aktif_borclar_sonraki_ay.append(borc)
                else: aktif_borclar_sonraki_ay.append(borc)
            else:
                min_borc_odeme_toplam += min_odeme_miktar
                faiz = borc['tutar'] * borc['faiz_aylik']; toplam_faiz_maliyeti += faiz
                if borc.get('min_kural') in ['FAIZ_ART_ANAPARA', 'FAIZ']: borc['tutar'] += faiz
                borc['tutar'] -= min_odeme_miktar
                aktif_borclar_sonraki_ay.append(borc)
        mevcut_borclar = aktif_borclar_sonraki_ay
        saldırı_gucu = max(0, toplam_gelir - zorunlu_gider_toplam - min_borc_odeme_toplam) * agresiflik_carpan + serbest_kalan_nakit_bu_ay
        saldırı_kalan = saldırı_gucu

        # Önceliklendirme
        # ... (Avalanche/Snowball sıralama mantığı buraya eklenebilir)
        mevcut_borclar.sort(key=lambda x: x.get('oncelik', 9999))

        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER'] and borc['tutar'] > 1 and saldırı_kalan > 0:
                odenecek = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odenecek; saldırı_kalan -= odenecek
                aylik_toplam_odemeler[borc['isim']] += odenecek

        mevcut_birikim += saldırı_kalan
        aylik_veri = {'Ay': ay_adi, 'Ek Ödeme Gücü': saldırı_gucu, 'Toplam Birikim': mevcut_birikim}
        for isim, tutar in aylik_gelir_dagilimi.items(): aylik_veri[isim] = tutar
        for b in borclar_initial: aylik_veri[b['isim']] = aylik_toplam_odemeler.get(b['isim'], 0)
        for b in borclar_initial:
            guncel_borc = next((item for item in mevcut_borclar if item['isim'] == b['isim']), None)
            aylik_veri[f"{b['isim']} (Kalan)"] = guncel_borc['tutar'] if guncel_borc and 'tutar' in guncel_borc else 0
        aylik_detaylar.append(aylik_veri)

    df_detay = pd.DataFrame(aylik_detaylar).fillna(0).round()
    return {"df": df_detay, "ay_sayisi": ay_sayisi, "toplam_faiz": toplam_faiz_maliyeti, "toplam_birikim": mevcut_birikim, "limit_asimi": limit_asimi}

# --- 7. Raporlama Fonksiyonları ---
def generate_report_and_recommendations(sonuc):
    tavsiyeler = []
    if sonuc['limit_asimi']: tavsiyeler.append("🚨 **ACİL DURUM:** Ödeme planı süresi 40 yılı aştı! Planınızı gözden geçirin.")
    elif sonuc['ay_sayisi'] <= 12: tavsiyeler.append("✅ **TEBRİKLER!** Borçlarınızı 1 yıldan kısa sürede kapatıyorsunuz.")
    excel_data = io.BytesIO()
    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
        sonuc['df'].to_excel(writer, index=False, sheet_name='Aylık_Akış')
    excel_data.seek(0)
    return {"tavsiyeler": tavsiyeler, "excel_data": excel_data}

# --- 8. Ana Uygulama Düzeni ---
st.title("Borç Kapatma ve Finansal Planlama")

st.header("🗂️ Profil Yönetimi (Yerel Kayıt)")
col_load, col_save = st.columns(2)
with col_load:
    uploaded_file = st.file_uploader("Yedekleme Dosyasını (JSON) Yükle", type=['json'], key="file_uploader_main")
    if uploaded_file: load_data_from_upload(uploaded_file)
with col_save:
    st.download_button(label="💾 Mevcut Verileri İndir", data=create_save_data(), file_name=f"finans_plan_{date.today().isoformat()}.json", mime="application/json")
st.markdown("---")

tab_basic, tab_advanced, tab_rules = st.tabs(["✨ Hızlı Planlama", "🚀 Gelişmiş Planlama", "⚙️ Kurallar"])

with tab_basic:
    st.header("Gelir ve Giderlerinizi Ekleyin")
    render_income_form("basic")
    st.markdown("---")
    # render_debt_form("basic") # Bu fonksiyonu kendi kodunuzdan ekleyin
    st.markdown("---")
    display_and_manage_items("basic", "gelirler")
    display_and_manage_items("basic", "borclar")
    st.markdown("---")
    if st.button("ÖDEME PLANINI OLUŞTUR", type="primary", key="calc_basic", disabled=not (st.session_state.borclar and st.session_state.gelirler)):
        st.session_state.run_simulation = True
        st.session_state.sim_params = {'agresiflik_carpan': 1.0} # Basit varsayılan

with tab_advanced:
    st.header("🚀 Gelişmiş Planlama ve Senaryo Yönetimi")
    col_st1, col_st2 = st.columns(2)
    with col_st1:
        AGRESIFLIK_ADVANCED = st.select_slider("Ek Ödeme Agresifliği", options=list(STRATEJILER.keys()), value="Maksimum Çaba (Tüm Ek Ödeme)", key='agresiflik_adv')
    with col_st2:
        # DÜZELTİLMİŞ SATIR
        AYLIK_ARTIS_ADVANCED = st.number_input("Birikim Yıllık Artış Yüzdesi (%)", min_value=0.0, value=3.5, step=0.1, key='aylik_artis_adv')
    
    # ... Diğer gelişmiş ayarlar ve formlar buraya eklenebilir ...

    if st.button("GELİŞMİŞ PLAN OLUŞTUR", type="primary", key="calc_adv", disabled=not (st.session_state.borclar and st.session_state.gelirler)):
        st.session_state.run_simulation = True
        st.session_state.sim_params = {'agresiflik_carpan': STRATEJILER[AGRESIFLIK_ADVANCED], 'birikim_artis_aylik': AYLIK_ARTIS_ADVANCED}

# --- 9. Hesaplama ve Raporlama ---
if st.session_state.get('run_simulation', False):
    params = st.session_state.get('sim_params', {})
    params['baslangic_tarihi'] = st.session_state.baslangic_tarihi
    sonuc = simule_borc_planı(st.session_state.borclar, st.session_state.gelirler, {}, **params)
    if sonuc:
        rapor = generate_report_and_recommendations(sonuc)
        st.markdown("---"); st.header("🏆 Rapor ve Sonuçlar")
        for tavsiye in rapor['tavsiyeler']: st.markdown(tavsiye)
        
        st.subheader("📋 Aylık Nakit Akışı ve Ödeme Planı")
        gelir_sutunlari = [g['isim'] for g in st.session_state.gelirler]
        gider_sutunlari = [b['isim'] for b in st.session_state.borclar]
        gosterilecek_sutunlar = ['Ay'] + gelir_sutunlari + gider_sutunlari + ['Ek Ödeme Gücü', 'Toplam Birikim']
        mevcut_sutunlar = [col for col in gosterilecek_sutunlar if col in sonuc['df'].columns]
        df_gosterim = sonuc['df'][mevcut_sutunlar].copy().rename(columns={'Ay': 'Ay (Gerçek Tarih)'})
        
        for col in df_gosterim.columns:
            if col != 'Ay (Gerçek Tarih)':
                df_gosterim[col] = df_gosterim[col].apply(format_tl)
        
        st.dataframe(df_gosterim, hide_index=True)
        st.download_button(label="⬇️ Excel İndir (Tüm Detaylar)", data=rapor['excel_data'], file_name=f"Borc_Odeme_Plani_{date.today().isoformat()}.xlsx")

    st.session_state.run_simulation = False # Bir sonraki çalıştırma için sıfırla
