import streamlit as st
import pandas as pd
import copy
import json
import io
import os
import re # Metin ayrıştırma için eklendi
from datetime import date
from dateutil.relativedelta import relativedelta

# --- 0. Yapılandırma ---
st.set_page_config(
    page_title="Borç Yönetimi ve Finansal Planlama",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 0.1 Kalıcılık Sabiti ---
DATA_FILE = 'finans_data.json'

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

# Para formatlama fonksiyonu
def format_tl(tutar):
    if pd.isna(tutar) or tutar is None:
        return "0 TL"
    # İYİLEŞTİRME: Türkçe formatı için virgül yerine nokta kullanımı
    return f"{int(tutar):,} TL".replace(",", ".")

# --- 2. Kalıcılık Fonksiyonları ---
def create_save_data():
    """st.session_state'i JSON formatında hazırlar."""
    # İYİLEŞTİRME: DataFrame'i serileştirmeden önce NaN değerlerini None ile değiştir
    harcama_df_serializable = st.session_state.harcama_kalemleri_df.where(pd.notnull(st.session_state.harcama_kalemleri_df), None)
    harcama_df_dict = harcama_df_serializable.to_dict(orient='split') # Split formatı daha güvenilir

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
    """Yüklenen dosyadan veriyi okur ve session state'e yükler."""
    if uploaded_file is not None:
        try:
            json_bytes = uploaded_file.read()
            data = json.loads(json_bytes.decode('utf-8'))

            st.session_state.borclar = data.get('borclar', [])
            st.session_state.gelirler = data.get('gelirler', [])

            df_dict = data.get('harcama_kalemleri_df', None)
            if df_dict and 'data' in df_dict and 'columns' in df_dict:
                 # Split formatından DataFrame'e geri dön
                st.session_state.harcama_kalemleri_df = pd.DataFrame(df_dict['data'], columns=df_dict['columns'], index=df_dict.get('index'))

            if 'tr_params' in data:
                st.session_state.tr_params.update(data['tr_params'])
            st.session_state.manuel_oncelik_listesi = data.get('manuel_oncelik_listesi', {})

            if 'baslangic_tarihi' in data:
                st.session_state.baslangic_tarihi = date.fromisoformat(data['baslangic_tarihi'])

            st.success(f"Veriler başarıyla yüklendi: {uploaded_file.name}")
            st.rerun()

        except Exception as e:
            st.error(f"Dosya okuma veya veri formatı hatası. Lütfen geçerli bir yedekleme dosyası yüklediğinizden emin olun. Hata: {e}")

# --- 2.1 Session State Başlatma ---
if 'borclar' not in st.session_state: st.session_state.borclar = []
if 'gelirler' not in st.session_state: st.session_state.gelirler = []
if 'harcama_kalemleri_df' not in st.session_state: st.session_state.harcama_kalemleri_df = pd.DataFrame({'Kalem Adı': ['Market', 'Ulaşım', 'Eğlence', 'Kişisel Bakım'], 'Aylık Bütçe (TL)': [15000, 3000, 2000, 1500]})
if 'tr_params' not in st.session_state: st.session_state.tr_params = {'kk_taksit_max_ay': 12, 'kk_asgari_odeme_yuzdesi_default': 20.0, 'kk_aylik_akdi_faiz': 3.66, 'kk_aylik_gecikme_faiz': 3.96, 'kmh_aylik_faiz': 5.0, 'kredi_taksit_max_ay': 36}
if 'manuel_oncelik_listesi' not in st.session_state: st.session_state.manuel_oncelik_listesi = {}
if 'baslangic_tarihi' not in st.session_state: st.session_state.baslangic_tarihi = date.today()


# --- 3. Yardımcı Fonksiyonlar ---
def hesapla_min_odeme(borc, faiz_carpani=1.0):
    kural = borc.get('min_kural')
    tutar = borc.get('tutar', 0)
    if kural in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
        return borc.get('sabit_taksit', 0)
    elif kural == 'ASGARI_FAIZ':
        asgari_anapara_yuzdesi = borc.get('kk_asgari_yuzdesi', 0)
        return tutar * asgari_anapara_yuzdesi
    elif kural in ['FAIZ_ART_ANAPARA', 'FAIZ']:
        zorunlu_anapara_yuzdesi = borc.get('zorunlu_anapara_yuzdesi', 0)
        return tutar * zorunlu_anapara_yuzdesi
    return 0

def add_debt(isim, faizli_anapara, oncelik_str, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi, kk_limit=0.0, devam_etme_yuzdesi=0.0):
    borc_listesi = []
    final_priority = 9999
    if oncelik_str:
        # İYİLEŞTİRME: Metin ayrıştırmayı daha sağlam hale getirelim.
        try:
            match = re.search(r'\d+', oncelik_str)
            if match:
                priority_val = int(match.group(0))
                final_priority = priority_val + 1000
            elif "En Yüksek Öncelik" in oncelik_str:
                final_priority = 1001
            else:
                 final_priority = 9999
        except Exception:
            final_priority = 9999
    yeni_borc = {
        "isim": isim, "tutar": faizli_anapara, "oncelik": final_priority, "faiz_aylik": faiz_aylik,
        "kalan_ay": kalan_ay if kalan_ay > 0 else 99999, "sabit_taksit": sabit_taksit,
        "kk_asgari_yuzdesi": kk_asgari_yuzdesi, "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi,
        "limit": kk_limit, "devam_etme_yuzdesi": devam_etme_yuzdesi
    }
    if borc_tipi == "Kredi Kartı Dönem Borcu (Faizli)":
        if faizli_anapara > 0:
            yeni_borc["isim"] = f"{isim} (Dönem Borcu)"
            yeni_borc["min_kural"] = "ASGARI_FAIZ"
            yeni_borc["faiz_aylik"] = st.session_state.tr_params['kk_aylik_akdi_faiz'] / 100.0
            yeni_borc["kk_asgari_yuzdesi"] = st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] / 100.0
            borc_listesi.append(yeni_borc)
    elif borc_tipi == "Ek Hesap (KMH)":
        yeni_borc["min_kural"] = "FAIZ_ART_ANAPARA"
        borc_listesi.append(yeni_borc)
    elif borc_tipi == "Kredi (Sabit Taksit/Anapara)":
        yeni_borc["min_kural"] = "SABIT_TAKSIT_ANAPARA"
        borc_listesi.append(yeni_borc)
    elif borc_tipi == "Diğer Faizli Borç":
        yeni_borc["min_kural"] = "FAIZ"
        borc_listesi.append(yeni_borc)
    elif borc_tipi in ["Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)", "Aylık Harcama Sepeti (Kütüphaneden)"]:
        yeni_borc["min_kural"] = "SABIT_GIDER"
        yeni_borc["oncelik"] = 1
        yeni_borc["tutar"] = 0
        yeni_borc["faiz_aylik"] = 0
        if borc_tipi == "Aylık Harcama Sepeti (Kütüphaneden)":
            yeni_borc["kalan_ay"] = 99999
        elif borc_tipi in ["Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)"]:
            yeni_borc["kalan_ay"] = kalan_ay if kalan_ay > 0 else 99999
        else:
            yeni_borc["kalan_ay"] = kalan_ay if 0 < kalan_ay < 99999 else 99999
        yeni_borc["sabit_taksit"] = sabit_taksit
        borc_listesi.append(yeni_borc)
    if borc_listesi:
        st.session_state.borclar.extend(borc_listesi)
        st.success(f"'{isim}' yükümlülüğü başarıyla eklendi.")
    else:
        st.warning(f"'{isim}' için eklenecek bir borç veya gider oluşturulamadı. (Tutar 0 olabilir)")

def add_income(isim, tutar, baslangic_ay, artis_yuzdesi, tek_seferlik):
    st.session_state.gelirler.append({
        "isim": isim, "tutar": tutar, "baslangic_ay": baslangic_ay,
        "artis_yuzdesi": artis_yuzdesi / 100.0, "tek_seferlik": tek_seferlik
    })
    st.success(f"'{isim}' gelir kaynağı başarıyla eklendi.")


# --- 4. Form Render Fonksiyonları ---
def render_income_form(context):
    st.subheader(f"Gelir Kaynağı Ekle")
    with st.form(f"new_income_form_{context}", clear_on_submit=True):
        col_i1, col_i2, col_i3 = st.columns(3)
        with col_i1:
            income_name = st.text_input("Gelir Kaynağı Adı", value="Maaş/Kira Geliri", key=f'inc_name_{context}')
            income_amount = st.number_input("Aylık Tutar", min_value=1.0, value=25000.0, key=f'inc_amount_{context}')
        with col_i2:
            income_start_month = st.number_input("Başlangıç Ayı (1=Şimdi)", min_value=1, value=1, key=f'inc_start_month_{context}')
            income_growth_perc = st.number_input("Yıllık Artış Yüzdesi (%)", min_value=0.0, value=10.0, step=0.5, key=f'inc_growth_perc_{context}')
        with col_i3:
            income_is_one_time = st.checkbox("Tek Seferlik Gelir Mi?", key=f'inc_one_time_{context}')
            st.markdown(" ")
            st.markdown(" ")
            if st.form_submit_button(label="Gelir Kaynağını Ekle"):
                add_income(income_name, income_amount, income_start_month, income_growth_perc, income_is_one_time)
                st.rerun()

def render_debt_form(context):
    st.subheader(f"Borçları ve Giderleri Yönet")
    kk_limit = 0.0; harcama_kalemleri_isim = ""; initial_faizli_tutar = 0.0; debt_taksit = 0.0
    debt_kalan_ay = 0; debt_faiz_aylik = 0.0; debt_kk_asgari_yuzdesi = 0.0
    debt_zorunlu_anapara_yuzdesi = 0.0; devam_etme_yuzdesi_input = 0.0; debt_priority_str = ""
    col_type_1, col_type_2 = st.columns([1, 2])
    with col_type_1:
        debt_name = st.text_input("Gider Kalemi Adı", value="Yeni Kalem", key=f'debt_name_{context}')
    with col_type_2:
        debt_type = st.selectbox("Gider Kalemi Tipi",
                                 ["Kredi Kartı Dönem Borcu (Faizli)", "Ek Hesap (KMH)", "Kredi (Sabit Taksit/Anapara)", "Diğer Faizli Borç",
                                  "--- Sabit Giderler (Zorunlu) ---",
                                  "Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)",
                                  "--- Aylık Harcama Sepeti ---",
                                  "Aylık Harcama Sepeti (Kütüphaneden)"],
                                 key=f'debt_type_{context}')
    if debt_type.startswith("---"):
        st.warning("Lütfen üstteki listeden faizli bir borç veya bir gider tipi seçin.")
        return
    with st.form(f"new_debt_form_{context}", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
        is_faizli_borc_ve_ek_odemeli = debt_type in ["Kredi Kartı Dönem Borcu (Faizli)", "Ek Hesap (KMH)", "Kredi (Sabit Taksit/Anapara)", "Diğer Faizli Borç"]
        with col_f1:
            if is_faizli_borc_ve_ek_odemeli:
                ek_odemeye_acik_borclar_info = [b['isim'] for b in st.session_state.borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']]
                ek_odemeye_acik_borclar_info.sort(key=lambda name: next((b['oncelik'] for b in st.session_state.borclar if b['isim'] == name), 9999))
                secenekler = ["1. En Yüksek Öncelik (Her Şeyden Önce)"]
                for i, isim in enumerate(ek_odemeye_acik_borclar_info):
                    secenekler.append(f"Öncelik {i+2}. {isim}'den sonra")
                secenekler.append(f"Öncelik {len(ek_odemeye_acik_borclar_info) + 2}. En Sona Bırak")
                varsayilan_index = len(secenekler)-1
                if ek_odemeye_acik_borclar_info:
                    debt_priority_str = st.selectbox("Ek Ödeme Sırası", options=secenekler, index=varsayilan_index, help="Bu kalemin, mevcut borçlara göre ek ödeme sırası neresi olmalı?", key=f'priority_select_{context}')
                else:
                    st.info("İlk ek ödeme borcunuz."); debt_priority_str = "1. En Yüksek Öncelik (Her Şeyden Önce)"
            else:
                st.info("Bu kalem için öncelik ayarı gerekmez (Gider/Taksit).")
        if debt_type == "Kredi Kartı Dönem Borcu (Faizli)":
            debt_taksit = 0.0; debt_kalan_ay = 0
            with col_f2:
                st.info("Kredi Kartı Detayları")
                kk_limit = st.number_input("Kart Limiti", min_value=1.0, value=150000.0, key=f'kk_limit_{context}')
                initial_faizli_tutar = st.number_input("Kalan Faizli Dönem Borcu (Anapara)", min_value=1.0, value=30000.0, key=f'kk_ekstre_{context}')
            with col_f3:
                st.info("Faiz Bilgisi (Yönetici Kuralları)")
                st.markdown(f"Aylık Faiz Oranı: **%{st.session_state.tr_params['kk_aylik_akdi_faiz']:.2f}**")
                st.markdown(f"Asgari Ödeme Yüzdesi: **%{st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default']:.1f}**")
                debt_faiz_aylik = st.session_state.tr_params['kk_aylik_akdi_faiz'] / 100.0
                debt_kk_asgari_yuzdesi = st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] / 100.0
        elif debt_type == "Ek Hesap (KMH)":
            kk_limit = 0.0; debt_kk_asgari_yuzdesi = 0.0; debt_taksit = 0.0; debt_kalan_ay = 0
            with col_f2:
                st.info("Ek Hesap (KMH) Detayları")
                kmh_limit_placeholder = st.number_input("Ek Hesap Limiti", min_value=1.0, value=50000.0, key=f'kmh_limit_{context}')
                initial_faizli_tutar = st.number_input("Kullanılan Anapara Tutarı", min_value=1.0, value=15000.0, key=f'initial_tutar_{context}')
            with col_f3:
                st.info("Faiz Bilgileri")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
                debt_zorunlu_anapara_yuzdesi = st.number_input("Zorunlu Anapara Kapama Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key=f'kmh_anapara_{context}') / 100.0
        elif debt_type == "Kredi (Sabit Taksit/Anapara)":
            kk_limit = 0.0; debt_kk_asgari_yuzdesi = 0.0; debt_zorunlu_anapara_yuzdesi = 0.0
            with col_f2:
                st.info("Kredi Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=1.0, value=50000.0, key=f'initial_tutar_{context}')
                debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=0.0, value=5000.0, key=f'sabit_taksit_{context}')
            with col_f3:
                st.info("Vade ve Faiz")
                max_taksit_ay_kredi = st.session_state.tr_params['kredi_taksit_max_ay']
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=0, max_value=max_taksit_ay_kredi, value=min(24, max_taksit_ay_kredi), key=f'kalan_taksit_ay_{context}')
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=4.5, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
        elif debt_type == "Diğer Faizli Borç":
            kk_limit = 0.0; debt_kk_asgari_yuzdesi = 0.0; debt_zorunlu_anapara_yuzdesi = 0.0
            with col_f2:
                st.info("Borç Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=1.0, value=10000.0, key=f'initial_tutar_{context}')
                debt_taksit = 0.0; debt_kalan_ay = 99999
            with col_f3:
                st.info("Faiz Bilgisi")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
        elif debt_type in ["Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)"]:
            initial_faizli_tutar = 0.0; debt_faiz_aylik = 0.0; debt_kk_asgari_yuzdesi = 0.0; debt_zorunlu_anapara_yuzdesi = 0.0; kk_limit = 0.0
            with col_f2:
                st.info("Gider Detayları")
                if debt_type == "Ev Kredisi Taksiti":
                    debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=1.0, value=25000.0, key=f'sabit_gider_tutar_{context}')
                    debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=120, key=f'kalan_taksit_ay_ev_{context}')
                elif debt_type == "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)":
                    debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=1.0, value=5000.0, key=f'sabit_gider_taksit_{context}')
                    debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=12, key=f'kalan_taksit_ay_{context}')
                else:
                    debt_taksit = st.number_input("Aylık Gider Tutarı", min_value=1.0, value=15000.0, key=f'sabit_gider_tutar_{context}')
                    debt_kalan_ay = 99999
            with col_f3:
                st.info("Kapanma Durumu")
                if debt_type == "Ev Kredisi Taksiti":
                    devam_etme_yuzdesi_input = st.number_input("Kredi Bitince Devam Yüzdesi (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f'devam_yuzdesi_{context}') / 100.0
                elif debt_type == "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)":
                    devam_etme_yuzdesi_input = st.number_input("Taksit Bitince Devam Yüzdesi (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f'devam_yuzdesi_taksit_{context}') / 100.0
                else:
                    st.markdown("Süresiz/Devam Eden Gider"); devam_etme_yuzdesi_input = 1.0
        elif debt_type == "Aylık Harcama Sepeti (Kütüphaneden)":
            initial_faizli_tutar = 0.0; debt_faiz_aylik = 0.0; debt_kk_asgari_yuzdesi = 0.0; debt_zorunlu_anapara_yuzdesi = 0.0; kk_limit = 0.0; debt_kalan_ay = 99999
            with col_f2:
                st.info("Harcama Kalemlerini Seçin")
                df_harcama = st.session_state.harcama_kalemleri_df
                kalem_isimleri = df_harcama['Kalem Adı'].tolist()
                secilen_kalemler = st.multiselect("Sepete Eklenecek Kalemler", options=kalem_isimleri, default=kalem_isimleri, key=f'harcama_multiselect_{context}')
                toplam_tutar = df_harcama[df_harcama['Kalem Adı'].isin(secilen_kalemler)]['Aylık Bütçe (TL)'].sum() if secilen_kalemler else 0.0
                debt_taksit = toplam_tutar
                harcama_kalemleri_isim = ", ".join(secilen_kalemler)
                st.markdown(f"**Toplam Aylık Harcama: {format_tl(debt_taksit)}**")
            with col_f3:
                st.info("Harcama Yönlendirmesi"); st.markdown("Bu harcamalar zorunlu gider olarak bütçenizden düşülür.")
                devam_etme_yuzdesi_input = 1.0
        st.markdown("---")
        if st.form_submit_button(label="Gider Kalemini Ekle"):
            if initial_faizli_tutar < 0 or debt_taksit < 0:
                st.error("Borç/Taksit tutarı negatif olamaz."); return
            final_debt_name = f"{debt_name} ({harcama_kalemleri_isim})" if debt_type == "Aylık Harcama Sepeti (Kütüphaneden)" else debt_name
            add_debt(isim=final_debt_name, faizli_anapara=initial_faizli_tutar, oncelik_str=debt_priority_str, borc_tipi=debt_type, sabit_taksit=debt_taksit, kalan_ay=debt_kalan_ay, faiz_aylik=debt_faiz_aylik, kk_asgari_yuzdesi=debt_kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi=debt_zorunlu_anapara_yuzdesi, kk_limit=kk_limit, devam_etme_yuzdesi=devam_etme_yuzdesi_input)
            st.rerun()

# --- 5. Görüntüleme ve Yönetim Fonksiyonları ---
def display_and_manage_debts(context_key):
    if st.session_state.borclar:
        st.subheader("📊 Mevcut Finansal Yükümlülükler")
        display_df = pd.DataFrame(st.session_state.borclar)
        cols_to_show = ['isim', 'min_kural', 'tutar', 'sabit_taksit', 'faiz_aylik', 'oncelik', 'kalan_ay']
        display_df_filtered = display_df[[col for col in cols_to_show if col in display_df.columns]]
        display_df_filtered.columns = ["Gider Kalemi Adı", "Kural", "Kalan Anapara", "Aylık Taksit/Gider", "Aylık Faiz (%)", "Öncelik", "Kalan Ay"]
        display_df_filtered['Kalan Anapara'] = display_df_filtered['Kalan Anapara'].apply(format_tl)
        display_df_filtered['Aylık Taksit/Gider'] = display_df_filtered['Aylık Taksit/Gider'].apply(format_tl)
        display_df_filtered['Aylık Faiz (%)'] = (display_df_filtered['Aylık Faiz (%)'].fillna(0.0) * 100).apply(lambda x: f"{x:.2f}%")
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        st.dataframe(display_df_filtered, hide_index=False, key=f"current_debts_df_{context_key}")
        st.info("Kaldırmak istediğiniz gider kalemlerinin solundaki **index numarasını** seçerek 'Sil' butonuna basın.")
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        debt_indices_to_delete = st.multiselect("Silinecek Gider Kaleminin Index Numarası", options=display_df.index.tolist(), key=f'debt_delete_select_{context_key}')
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        if st.button(f"Seçili Gider Kalemini Sil", type="secondary", key=f'delete_button_{context_key}'):
            if not debt_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz gider kalemlerinin index numarasını seçin."); return
            st.session_state.borclar = [borc for i, borc in enumerate(st.session_state.borclar) if i not in debt_indices_to_delete]
            st.success(f"{len(debt_indices_to_delete)} adet gider kalemi listeden kaldırıldı.")
            st.rerun()
    else:
        st.info("Henüz eklenmiş bir borç veya gider kalemi bulunmamaktadır.")

def display_and_manage_incomes(context_key):
    if st.session_state.gelirler:
        st.subheader("💰 Mevcut Gelir Kaynakları")
        gelir_df = pd.DataFrame(st.session_state.gelirler)
        gelir_df = gelir_df[['isim', 'tutar', 'baslangic_ay', 'artis_yuzdesi', 'tek_seferlik']]
        gelir_df.columns = ["Gelir Adı", "Aylık Tutar", "Başlangıç Ayı", "Artış Yüzdesi", "Tek Seferlik Mi?"]
        gelir_df['Aylık Tutar'] = gelir_df['Aylık Tutar'].apply(format_tl)
        gelir_df['Artış Yüzdesi'] = (gelir_df['Artış Yüzdesi'] * 100).apply(lambda x: f"{x:.2f}%")
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        st.dataframe(gelir_df, hide_index=False, key=f"current_incomes_df_{context_key}")
        st.info("Kaldırmak istediğiniz gelirlerin solundaki **index numarasını** seçerek 'Sil' butonuna basın.")
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        income_indices_to_delete = st.multiselect("Silinecek Gelirin Index Numarası", options=gelir_df.index.tolist(), key=f'income_delete_select_{context_key}')
        # DÜZELTME: Widget'ın anahtarını (key) context_key ile benzersiz hale getirelim.
        if st.button(f"Seçili Geliri Sil", type="secondary", key=f'delete_income_button_{context_key}'):
            if not income_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz gelirlerin index numarasını seçin."); return
            st.session_state.gelirler = [gelir for i, gelir in enumerate(st.session_state.gelirler) if i not in income_indices_to_delete]
            st.success(f"{len(income_indices_to_delete)} adet gelir listeden kaldırıldı.")
            st.rerun()
    else:
        st.info("Henüz eklenmiş bir gelir kaynağı bulunmamaktadır.")


# --- 6. Borç Ödeme Planı Hesaplama Fonksiyonu ---
def simule_borc_planı(borclar_initial, gelirler_initial, manuel_oncelikler, **sim_params):
    if not borclar_initial or not gelirler_initial:
        return None
    total_birikim_hedefi = sim_params.get('total_birikim_hedefi', 0.0)
    birikim_tipi_str = sim_params.get('birikim_tipi_str', 'Aylık Sabit Tutar')
    baslangic_tarihi = sim_params.get('baslangic_tarihi', date.today())
    mevcut_borclar = copy.deepcopy(borclar_initial)
    mevcut_gelirler = copy.deepcopy(gelirler_initial)
    if sim_params.get('oncelik_stratejisi') == 'Kullanici':
        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'] and borc['isim'] in manuel_oncelikler:
                borc['oncelik'] = manuel_oncelikler[borc['isim']]
    ay_sayisi = 0; mevcut_birikim = sim_params.get('baslangic_birikim', 0.0)
    birikime_ayrilan = sim_params.get('aylik_zorunlu_birikim', 0.0); faiz_carpani = sim_params.get('faiz_carpani', 1.0)
    agresiflik_carpan = sim_params.get('agresiflik_carpan', 1.0); birikim_artis_aylik = sim_params.get('birikim_artis_aylik', 0.0) / 12 / 100
    toplam_faiz_maliyeti = 0.0
    baslangic_faizli_borc = sum(b['tutar'] for b in borclar_initial if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    aylik_detaylar = []; limit_asimi = False
    while True:
        ay_sayisi += 1
        rapor_tarihi = baslangic_tarihi + relativedelta(months=ay_sayisi - 1)
        ay_adi = rapor_tarihi.strftime("%b %Y")
        borc_tamamlandi = not any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
        birikim_hedefi_tamamlandi = (mevcut_birikim >= total_birikim_hedefi) if birikim_tipi_str == "Borç Bitimine Kadar Toplam Tutar" else True
        if ay_sayisi > 1 and borc_tamamlandi and birikim_hedefi_tamamlandi: break
        if ay_sayisi > 360: limit_asimi = True; break
        toplam_gelir = 0.0; aylik_gelir_dagilimi = {}
        for gelir in mevcut_gelirler:
            if ay_sayisi >= gelir['baslangic_ay']:
                artis_carpan = (1 + gelir['artis_yuzdesi']) ** ((ay_sayisi - gelir['baslangic_ay']) / 12)
                gelir_tutari = gelir['tutar'] * artis_carpan
                if gelir['tek_seferlik'] and ay_sayisi != gelir['baslangic_ay']: gelir_tutari = 0.0
                aylik_gelir_dagilimi[gelir['isim']] = round(gelir_tutari)
                toplam_gelir += gelir_tutari
        zorunlu_gider_toplam = birikime_ayrilan; min_borc_odeme_toplam = 0.0
        aktif_borclar_sonraki_ay = []; serbest_kalan_nakit_bu_ay = 0.0
        # YENİ: Her bir borç için o ay yapılan toplam ödemeyi saklamak için
        aylik_toplam_odemeler = {b['isim']: 0 for b in borclar_initial}
        for borc in mevcut_borclar:
            min_odeme_miktar = hesapla_min_odeme(borc, faiz_carpani)
            aylik_toplam_odemeler[borc['isim']] = min_odeme_miktar
            is_sureli_gider = borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'] and borc.get('kalan_ay', 99999) < 99999
            if borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                zorunlu_gider_toplam += min_odeme_miktar
            else:
                min_borc_odeme_toplam += min_odeme_miktar
                etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani
                if borc['min_kural'] in ['FAIZ_ART_ANAPARA', 'FAIZ']: borc['tutar'] += eklenen_faiz
                toplam_faiz_maliyeti += eklenen_faiz; borc['tutar'] -= min_odeme_miktar
            if is_sureli_gider:
                if borc['kalan_ay'] > 1: borc['kalan_ay'] -= 1; aktif_borclar_sonraki_ay.append(borc)
            else:
                aktif_borclar_sonraki_ay.append(borc)
        mevcut_borclar = aktif_borclar_sonraki_ay
        kalan_nakit = toplam_gelir - zorunlu_gider_toplam - min_borc_odeme_toplam
        saldırı_gucu = max(0, kalan_nakit * agresiflik_carpan) + serbest_kalan_nakit_bu_ay
        saldırı_kalan = saldırı_gucu
        if sim_params['oncelik_stratejisi'] == 'Avalanche': mevcut_borclar.sort(key=lambda x: (x.get('faiz_aylik', 0), x.get('tutar', 0)), reverse=True)
        elif sim_params['oncelik_stratejisi'] == 'Snowball': mevcut_borclar.sort(key=lambda x: x.get('tutar', float('inf')) if x.get('tutar', 0) > 1 else float('inf'))
        else: mevcut_borclar.sort(key=lambda x: x.get('oncelik', float('inf')))
        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                if borc['tutar'] > 1 and saldırı_kalan > 0:
                    odecek_tutar = min(saldırı_kalan, borc['tutar'])
                    borc['tutar'] -= odecek_tutar; saldırı_kalan -= odecek_tutar
                    aylik_toplam_odemeler[borc['isim']] += odecek_tutar
        mevcut_birikim += saldırı_kalan; mevcut_birikim *= (1 + birikim_artis_aylik)
        # YENİ YAPI: Raporlamayı nakit akışı formatında oluştur
        aylik_veri = {'Ay': ay_adi, 'Ek Ödeme Gücü': round(saldırı_gucu), 'Toplam Birikim': round(mevcut_birikim)}
        for isim, tutar in aylik_gelir_dagilimi.items(): aylik_veri[isim] = tutar
        for b in borclar_initial: aylik_veri[b['isim']] = round(aylik_toplam_odemeler.get(b['isim'], 0))
        # Excel için Kalan Borç verisini saklamaya devam et
        for b in borclar_initial:
            guncel_borc = next((item for item in mevcut_borclar if item['isim'] == b['isim']), None)
            kalan_tutar = round(guncel_borc['tutar']) if guncel_borc else 0
            aylik_veri[f"{b['isim']} (Kalan)"] = kalan_tutar if b.get('min_kural') not in ['SABIT_GIDER'] else 0
        aylik_detaylar.append(aylik_veri)
    df_detay = pd.DataFrame(aylik_detaylar).fillna(0)
    ilk_ay_toplam_gelir = df_detay.iloc[0][[g['isim'] for g in gelirler_initial]].sum() if not df_detay.empty else 0
    ilk_ay_toplam_gider = df_detay.iloc[0][[b['isim'] for b in borclar_initial]].sum() if not df_detay.empty else 0
    return {"df": df_detay, "ay_sayisi": ay_sayisi, "toplam_faiz": round(toplam_faiz_maliyeti), "toplam_birikim": round(mevcut_birikim), "baslangic_faizli_borc": round(baslangic_faizli_borc), "ilk_ay_gelir": ilk_ay_toplam_gelir, "ilk_ay_gider": ilk_ay_toplam_gider, "limit_asimi": limit_asimi}

# --- YENİ RAPORLAMA VE TAVSİYE FONKSİYONLARI ---
def run_alternative_scenario(borclar, gelirler, current_params, new_strategy_name, new_agresiflik_name):
    agresiflik_carpan = STRATEJILER[new_agresiflik_name]
    oncelik_stratejisi = ONCELIK_STRATEJILERI.get(new_strategy_name, current_params['oncelik_stratejisi'])
    sim_params = copy.deepcopy(current_params)
    sim_params.update({'agresiflik_carpan': agresiflik_carpan, 'oncelik_stratejisi': oncelik_stratejisi})
    sonuc = simule_borc_planı(borclar, gelirler, {}, **sim_params)
    return {'isim': f"{new_strategy_name} ({new_agresiflik_name})", 'ay_sayisi': sonuc['ay_sayisi'], 'toplam_faiz': sonuc['toplam_faiz'], 'toplam_birikim': sonuc['toplam_birikim']}

def generate_report_and_recommendations(sonuc, current_params):
    alternatifler = []; tavsiyeler = []
    current_strat_list = [k for k, v in ONCELIK_STRATEJILERI.items() if v == current_params['oncelik_stratejisi']]
    current_strat = current_strat_list[0] if current_strat_list else "Kullanıcı Tanımlı Sıra"
    current_agresiflik_val = current_params['agresiflik_carpan']
    current_agresiflik_name_list = [k for k, v in STRATEJILER.items() if v == current_agresiflik_val]
    current_agresiflik_name = current_agresiflik_name_list[0] if current_agresiflik_name_list else "Maksimum Çaba (Tüm Ek Ödeme)"
    if sonuc['limit_asimi']: tavsiyeler.append("🚨 **ACİL DURUM:** Ödeme planı süresi 30 yılı aştı! Mevcut gelir ve gider yapınızla borçlarınızı kapatmanız mümkün görünmüyor. **Gelir artışı veya sabit giderlerde ciddi kesintiler** yapmayı düşünün.")
    elif sonuc['ay_sayisi'] <= 12: tavsiyeler.append("✅ **TEBRİKLER!** Borçlarınızı bir yıldan kısa sürede kapatıyorsunuz. Finansal olarak çok iyi bir yoldasınız.")
    excel_data = io.BytesIO()
    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
        sonuc['df'].to_excel(writer, index=False, sheet_name='Aylık Finansal Akış')
    excel_data.seek(0)
    return {"alternatifler": alternatifler, "tavsiyeler": tavsiyeler, "excel_data": excel_data}


# --- 7. Ana Uygulama Düzeni ---
st.title("Borç Kapatma ve Finansal Ödeme Planı")
st.header("🗂️ Profil Yönetimi (Yerel Kayıt)")
st.info("Bu uygulama, verilerinizi hiçbir sunucuda saklamaz. Uygulamadan çıkmadan önce **Mevcut Verileri İndir** butonuna basarak yedek alın ve geri dönmek istediğinizde bu dosyayı yükleyin.")
col_load, col_save = st.columns(2)
with col_load:
    uploaded_file = st.file_uploader("Yedekleme Dosyasını (JSON) Yükle", type=['json'], key="file_uploader_main")
    if uploaded_file:
        load_data_from_upload(uploaded_file)
with col_save:
    st.markdown(" "); data_to_save = create_save_data()
    st.download_button(label="💾 Mevcut Verileri İndir (Yedekleme)", data=data_to_save, file_name=f"finans_plan_yedekleme_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json", mime="application/json")
st.markdown("---")
st.subheader("🗓️ Plan Başlangıç Tarihini Ayarla")
st.session_state.baslangic_tarihi = st.date_input("Ödeme planı hangi ay başlasın?", value=st.session_state.baslangic_tarihi, key='date_input_main')
st.markdown("---")
tab_basic, tab_advanced, tab_rules = st.tabs(["✨ Basit Planlama (Başlangıç)", "🚀 Gelişmiş Planlama", "⚙️ Yönetici Kuralları"])

with tab_basic:
    st.header("✨ Hızlı ve Varsayılan Planlama")
    render_income_form("basic"); st.markdown("---"); render_debt_form("basic")
    st.markdown("---"); display_and_manage_incomes("basic"); display_and_manage_debts("basic")
    st.markdown("---")
    is_disabled_basic = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_basic = st.button("ÖDEME PLANINI OLUŞTUR", type="primary", disabled=is_disabled_basic, key="calc_basic")

with tab_advanced:
    st.header("🚀 Gelişmiş Planlama ve Senaryo Yönetimi")
    col_st1, col_st2, col_st3 = st.columns(3)
    with col_st1: AGRESIFLIK_ADVANCED = st.selectbox("Ek Ödeme Agresifliği", options=list(STRATEJILER.keys()), index=2, key='agresiflik_adv'); ONCELIK_ADVANCED = st.selectbox("Borç Kapatma Yöntemi", options=list(ONCELIK_STRATEJILERI.keys()), index=0, key='oncelik_adv')
    with col_st2: FAIZ_CARPANI_ADVANCED = st.slider("Faiz Oranı Çarpanı", 0.5, 2.0, 1.0, 0.1, key='faiz_carpan_adv'); AYLIK_ARTIS_ADVANCED = st.number_input("Birikim Yıllık Artış Yüzdesi (%)", 3.5, 0.0, step=0.1, key='aylik_artis_adv')
    with col_st3: BIRIKIM_TIPI_ADVANCED = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_adv'); AYLIK_ZORUNLU_BIRIKIM_ADVANCED = st.number_input("Aylık Zorunlu Birikim Tutarı", 5000, 0, step=500, key='zorunlu_birikim_aylik_adv', disabled=BIRIKIM_TIPI_ADVANCED != "Aylık Sabit Tutar"); TOPLAM_BIRIKIM_HEDEFI_ADVANCED = st.number_input("Hedef Toplam Birikim Tutarı", 50000, 0, step=5000, key='zorunlu_birikim_toplam_adv', disabled=BIRIKIM_TIPI_ADVANCED != "Borç Bitimine Kadar Toplam Tutar"); BASLANGIC_BIRIKIM_ADVANCED = st.number_input("Mevcut Başlangıç Birikimi", 0, 0, step=1000, key='baslangic_birikim_adv')
    st.markdown("---"); render_income_form("advanced"); st.markdown("---"); render_debt_form("advanced"); st.markdown("---")
    st.subheader("🛠️ Manuel Borç Kapatma Sırası (Gelişmiş)")
    if ONCELIK_ADVANCED == "Kullanıcı Tanımlı Sıra":
        odemeye_acik_borclar = [b for b in st.session_state.borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']]
        if odemeye_acik_borclar:
            siralama_df = pd.DataFrame([{'isim': b['isim'], 'yeni_oncelik': st.session_state.manuel_oncelik_listesi.get(b['isim'], b['oncelik'] - 1000)} for b in odemeye_acik_borclar]).sort_values(by='yeni_oncelik')
            st.info("Borç önceliklerini manuel olarak ayarlamak için **'Yeni Öncelik'** sütunundaki numaraları değiştirin.")
            edited_siralama_df = st.data_editor(siralama_df, column_config={"yeni_oncelik": st.column_config.NumberColumn("Yeni Öncelik", min_value=1, step=1), "isim": st.column_config.TextColumn("Borç Adı", disabled=True)}, hide_index=True, key='advanced_priority_editor')
            st.session_state.manuel_oncelik_listesi = edited_siralama_df.set_index('isim')['yeni_oncelik'].apply(lambda x: x + 1000).to_dict()
        else: st.info("Ek ödemeye açık borç bulunmamaktadır.")
    else: st.info("Manuel sıralama, sadece **'Kullanıcı Tanımlı Sıra'** seçildiğinde geçerlidir.")
    st.markdown("---"); display_and_manage_incomes("advanced"); display_and_manage_debts("advanced"); st.markdown("---")
    is_disabled_advanced = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_advanced = st.button("ÖDEME PLANINI OLUŞTUR", type="primary", disabled=is_disabled_advanced, key="calc_adv")

with tab_rules:
    st.header("Ödeme Planı Kurallarını Yönet")
    st.subheader("🇹🇷 BDDK ve Yasal Limitler (Türkiye)")
    col_l1, col_l2, col_l3 = st.columns(3)
    with col_l1: st.session_state.tr_params['kk_aylik_akdi_faiz'] = st.number_input("KK Aylık Akdi Faiz (%)", 0.0, value=st.session_state.tr_params['kk_aylik_akdi_faiz'], step=0.01, key='bddk_kk_faiz')
    with col_l2: st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] = st.number_input("KK Asgari Ödeme Yüzdesi (%)", 0.0, 100.0, value=st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'], step=1.0, key='bddk_kk_asgari_yuzde')
    with col_l3: st.session_state.tr_params['kmh_aylik_faiz'] = st.number_input("KMH/Kredi Piyasa Faizi (%)", 0.0, value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.1, key='bddk_kmh_faiz')
    st.markdown("---")
    st.subheader("💳 Aylık Harcama Kalemleri Kütüphanesi")
    edited_df = st.data_editor(st.session_state.harcama_kalemleri_df, column_config={"Kalem Adı": st.column_config.TextColumn("Kalem Adı", required=True), "Aylık Bütçe (TL)": st.column_config.NumberColumn("Aylık Bütçe (TL)", min_value=0, step=100, format="%d TL")}, num_rows="dynamic", hide_index=True, key='harcama_editor')
    st.session_state.harcama_kalemleri_df = edited_df

# --- 8. Hesaplama Tetikleyicileri ---
if calculate_button_advanced or calculate_button_basic:
    sim_params = {}
    if calculate_button_advanced:
        manuel_oncelikler = st.session_state.manuel_oncelik_listesi
        sim_params = {'agresiflik_carpan': STRATEJILER[AGRESIFLIK_ADVANCED], 'oncelik_stratejisi': ONCELIK_STRATEJILERI[ONCELIK_ADVANCED], 'faiz_carpani': FAIZ_CARPANI_ADVANCED, 'birikim_artis_aylik': AYLIK_ARTIS_ADVANCED, 'aylik_zorunlu_birikim': AYLIK_ZORUNLU_BIRIKIM_ADVANCED if BIRIKIM_TIPI_ADVANCED == "Aylık Sabit Tutar" else 0, 'baslangic_birikim': BASLANGIC_BIRIKIM_ADVANCED, 'total_birikim_hedefi': TOPLAM_BIRIKIM_HEDEFI_ADVANCED, 'birikim_tipi_str': BIRIKIM_TIPI_ADVANCED}
    else: # Basit Planlama
        manuel_oncelikler = {}
        sim_params = {'agresiflik_carpan': STRATEJILER.get("Maksimum Çaba (Tüm Ek Ödeme)"), 'oncelik_stratejisi': ONCELIK_STRATEJILERI.get("Borç Çığı (Avalanche - Önce Faiz)"), 'faiz_carpani': 1.0, 'birikim_artis_aylik': 3.5, 'aylik_zorunlu_birikim': 0, 'baslangic_birikim': 0, 'total_birikim_hedefi': 0, 'birikim_tipi_str': "Aylık Sabit Tutar"}
    sim_params['baslangic_tarihi'] = st.session_state.baslangic_tarihi
    sonuc = simule_borc_planı(st.session_state.borclar, st.session_state.gelirler, manuel_oncelikler, **sim_params)
    if sonuc:
        rapor_sonuclari = generate_report_and_recommendations(sonuc, sim_params)
        with st.container():
            st.markdown("---"); st.header("🏆 Borç Yönetimi Karşılaştırmalı Raporu")
            if sonuc.get('limit_asimi'): st.error("‼️ Ödeme planı süresi 30 yılı aştı.")
            else: st.success("✅ Ödeme planınız başarıyla oluşturuldu!")
            st.subheader("💡 Kişiselleştirilmiş Tavsiyeler ve Analiz")
            for tavsiye in rapor_sonuclari['tavsiyeler']: st.markdown(tavsiye)
            st.markdown("---")
            # --- YENİ YAPI: Ana Rapor Tablosu ---
            st.subheader("📋 Aylık Nakit Akışı ve Ödeme Planı")
            gelir_sutunlari = [g['isim'] for g in st.session_state.gelirler]
            gider_sutunlari = [b['isim'] for b in st.session_state.borclar]
            gosterilecek_sutunlar = ['Ay'] + gelir_sutunlari + gider_sutunlari + ['Ek Ödeme Gücü', 'Toplam Birikim']
            mevcut_sutunlar = [col for col in gosterilecek_sutunlar if col in sonuc['df'].columns]
            df_gosterim = sonuc['df'][mevcut_sutunlar].copy()
            df_gosterim = df_gosterim.rename(columns={'Ay': 'Ay (Gerçek Tarih)'})
            for col in df_gosterim.columns:
                if col != 'Ay (Gerçek Tarih)':
                    df_gosterim[col] = df_gosterim[col].apply(lambda x: format_tl(x) if isinstance(x, (int, float)) else x)
            col_res1, col_res2 = st.columns([3, 1])
            with col_res2:
                st.download_button(label="⬇️ Excel İndir (Tüm Detaylar)", data=rapor_sonuclari['excel_data'], file_name=f"Borc_Odeme_Plani_Detay_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col_res1:
                st.dataframe(df_gosterim, hide_index=True)

# --- DIPNOT VE TELİF ---
st.markdown("---")
st.markdown("""
<div style='text-align: center; font-size: small; color: gray;'>
    Bu gelişmiş finansal planlama aracı, bireysel finansal stratejileri güçlendirmek amacıyla titizlikle hazırlanmıştır.
</div>
""", unsafe_allow_html=True)
