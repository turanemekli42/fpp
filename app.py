import streamlit as st
import pandas as pd
import copy
import json
import io 
import os

# --- 0. Yapılandırma ---
st.set_page_config(
    page_title="Borç Yönetimi Simülasyonu",
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
    # NumPy'den gelen float değerlerini integer'a çevirip formatlama
    return f"{int(tutar):,} TL"

# --- 2. Kalıcılık Fonksiyonları ---

def create_save_data():
    """st.session_state'i JSON formatında hazırlar."""
    data = {
        'borclar': st.session_state.borclar,
        'gelirler': st.session_state.gelirler,
        'harcama_kalemleri_df': st.session_state.harcama_kalemleri_df.to_dict(),
        'tr_params': st.session_state.tr_params,
        'manuel_oncelik_listesi': st.session_state.manuel_oncelik_listesi
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
            if df_dict:
                 st.session_state.harcama_kalemleri_df = pd.DataFrame.from_dict(df_dict)
            
            if 'tr_params' in data:
                st.session_state.tr_params.update(data['tr_params'])
            st.session_state.manuel_oncelik_listesi = data.get('manuel_oncelik_listesi', {})
            
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
        try:
            priority_val = int(oncelik_str.split('.')[0].split(' ')[-1])
            final_priority = priority_val + 1000 
        except:
            if "1. En Yüksek Öncelik" in oncelik_str:
                final_priority = 1001
            else:
                final_priority = 9999
    
    # Borç objesini oluştur
    yeni_borc = {
        "isim": isim,
        "tutar": faizli_anapara,
        "oncelik": final_priority,
        "faiz_aylik": faiz_aylik,
        "kalan_ay": kalan_ay if kalan_ay > 0 else 99999,
        "sabit_taksit": sabit_taksit,
        "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
        "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi,
        "limit": kk_limit,
        "devam_etme_yuzdesi": devam_etme_yuzdesi
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
        
        # Kalan ay ayarları
        if borc_tipi == "Aylık Harcama Sepeti (Kütüphaneden)":
            yeni_borc["kalan_ay"] = 99999
        elif borc_tipi == "Ev Kredisi Taksiti" or borc_tipi == "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)":
             yeni_borc["kalan_ay"] = kalan_ay if kalan_ay > 0 else 99999
        else: # Kira, Aidat vb.
            yeni_borc["kalan_ay"] = kalan_ay if kalan_ay < 99999 and kalan_ay > 0 else 99999
             
        yeni_borc["sabit_taksit"] = sabit_taksit
        borc_listesi.append(yeni_borc)

    if borc_listesi:
        st.session_state.borclar.extend(borc_listesi)
        st.success(f"'{isim}' yükümlülüğü başarıyla eklendi.")
    else:
        st.warning(f"'{isim}' için eklenecek bir borç veya gider oluşturulamadı. (Tutar 0 olabilir)")


def add_income(isim, tutar, baslangic_ay, artis_yuzdesi, tek_seferlik):
    st.session_state.gelirler.append({
        "isim": isim,
        "tutar": tutar,
        "baslangic_ay": baslangic_ay,
        "artis_yuzdesi": artis_yuzdesi / 100.0,
        "tek_seferlik": tek_seferlik
    })
    st.success(f"'{isim}' gelir kaynağı başarıyla eklendi.")


# --- 4. Form Render Fonksiyonları ---

def render_income_form(context):
    st.subheader(f"Gelir Kaynağı Ekle ({context})")
    
    with st.form(f"new_income_form_{context}", clear_on_submit=True):
        col_i1, col_i2, col_i3 = st.columns(3)
        
        with col_i1:
            income_name = st.text_input("Gelir Kaynağı Adı", value="Maaş/Kira Geliri", key=f'inc_name_{context}')
            # Veri Kontrolü: Tutar > 1.0 olmalı
            income_amount = st.number_input("Aylık Tutar", min_value=1.0, value=25000.0, key=f'inc_amount_{context}') 
            
        with col_i2:
            income_start_month = st.number_input("Başlangıç Ayı (1=Şimdi)", min_value=1, value=1, key=f'inc_start_month_{context}')
            income_growth_perc = st.number_input("Yıllık Artış Yüzdesi (%)", min_value=0.0, value=10.0, step=0.5, key=f'inc_growth_perc_{context}')
            
        with col_i3:
            income_is_one_time = st.checkbox("Tek Seferlik Gelir Mi? (Bonus, İkramiye vb.)", key=f'inc_one_time_{context}')
            st.markdown(" ")
            st.markdown(" ")
            
            submit_button = st.form_submit_button(label="Gelir Kaynağını Ekle")
            
        if submit_button:
            add_income(income_name, income_amount, income_start_month, income_growth_perc, income_is_one_time)
            st.rerun()


def render_debt_form(context):
    st.subheader(f"Borçları ve Giderleri Yönet ({context})")
    
    # Tüm olası değişkenleri form başında None veya 0 olarak başlatalım
    kk_limit = 0.0
    harcama_kalemleri_isim = ""
    initial_faizli_tutar = 0.0
    debt_taksit = 0.0
    debt_kalan_ay = 0
    debt_faiz_aylik = 0.0
    debt_kk_asgari_yuzdesi = 0.0
    debt_zorunlu_anapara_yuzdesi = 0.0
    devam_etme_yuzdesi_input = 0.0
    debt_priority_str = ""

    with st.form(f"new_debt_form_{context}", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        
        # --- SÜTUN 1: TİP SEÇİMİ VE ÖNCELİK (HER ZAMAN GÖRÜNÜR) ---
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Yükümlülük", key=f'debt_name_{context}')
            
            debt_type = st.selectbox("Yükümlülük Tipi",
                                     ["Kredi Kartı Dönem Borcu (Faizli)", "Ek Hesap (KMH)", "Kredi (Sabit Taksit/Anapara)", "Diğer Faizli Borç",
                                      "--- Sabit Giderler (Zorunlu) ---",
                                      "Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)",
                                      "--- Aylık Harcama Sepeti ---",
                                      "Aylık Harcama Sepeti (Kütüphaneden)"], 
                                     key=f'debt_type_{context}')
            
            is_faizli_borc_ve_ek_odemeli = debt_type in ["Kredi Kartı Dönem Borcu (Faizli)", "Ek Hesap (KMH)", "Kredi (Sabit Taksit/Anapara)", "Diğer Faizli Borç"]
            
            if is_faizli_borc_ve_ek_odemeli:
                ek_odemeye_acik_borclar_info = [
                    (b['isim'], b['oncelik']) for b in st.session_state.borclar
                    if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
                ]
                ek_odemeye_acik_borclar_info.sort(key=lambda x: x[1])
                secenekler = ["1. En Yüksek Öncelik (Her Şeyden Önce)"]
                for i, (isim, oncelik) in enumerate(ek_odemeye_acik_borclar_info):
                    secenekler.append(f"Öncelik {i+2}. {isim}'den sonra")
                secenekler.append(f"Öncelik {len(ek_odemeye_acik_borclar_info) + 2}. En Sona Bırak") 
                
                varsayilan_index = len(secenekler)-1

                if ek_odemeye_acik_borclar_info:
                    debt_priority_str = st.selectbox("Ek Ödeme Sırası", options=secenekler, index=varsayilan_index,
                                                     help="Bu borcun, mevcut borçlara göre ek ödeme sırası neresi olmalı?", key=f'priority_select_{context}')
                else:
                    debt_priority_str = "1. En Yüksek Öncelik (Her Şeyden Önce)" 

        # --- SÜTUN 2 & 3: DİNAMİK ALANLAR ---
        
        # Seçim grupları için uyarı göster
        if debt_type.startswith("---"):
             with col_f2:
                 st.warning("Lütfen üstteki listeden faizli bir borç veya bir gider tipi seçin.")
                 
        # KK Dönem Borcu (SADELEŞTİRİLMİŞ)
        elif debt_type == "Kredi Kartı Dönem Borcu (Faizli)":
            debt_taksit = 0.0
            debt_kalan_ay = 0
            
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


        # Ek Hesap (KMH)
        elif debt_type == "Ek Hesap (KMH)":
            kk_limit = 0.0
            debt_kk_asgari_yuzdesi = 0.0 
            debt_taksit = 0.0
            debt_kalan_ay = 0 

            with col_f2:
                st.info("Ek Hesap (KMH) Detayları")
                kmh_limit_placeholder = st.number_input("Ek Hesap Limiti", min_value=1.0, value=50000.0, key=f'kmh_limit_{context}')
                initial_faizli_tutar = st.number_input("Kullanılan Anapara Tutarı", min_value=1.0, value=15000.0, key=f'initial_tutar_{context}')
            with col_f3:
                st.info("Faiz Bilgileri")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
                debt_zorunlu_anapara_yuzdesi = st.number_input("Zorunlu Anapara Kapama Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key=f'kmh_anapara_{context}') / 100.0

        # Kredi (Sabit Taksit/Anapara)
        elif debt_type == "Kredi (Sabit Taksit/Anapara)":
            kk_limit = 0.0
            debt_kk_asgari_yuzdesi = 0.0 
            debt_zorunlu_anapara_yuzdesi = 0.0
            
            with col_f2:
                st.info("Kredi Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=1.0, value=50000.0, key=f'initial_tutar_{context}')
                debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=0.0, value=5000.0, key=f'sabit_taksit_{context}')
            with col_f3:
                st.info("Vade ve Faiz")
                max_taksit_ay_kredi = st.session_state.tr_params['kredi_taksit_max_ay']
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=0, max_value=max_taksit_ay_kredi, value=min(24, max_taksit_ay_kredi), key=f'kalan_taksit_ay_{context}')
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=4.5, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0

        # Diğer Faizli Borç
        elif debt_type == "Diğer Faizli Borç":
            kk_limit = 0.0
            debt_kk_asgari_yuzdesi = 0.0 
            debt_zorunlu_anapara_yuzdesi = 0.0
            
            with col_f2:
                st.info("Borç Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=1.0, value=10000.0, key=f'initial_tutar_{context}')
                debt_taksit = 0.0
                debt_kalan_ay = 99999 
            with col_f3:
                st.info("Faiz Bilgisi")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
        
        # --- ZORUNLU SABİT GİDERLER ---
        elif debt_type in ["Zorunlu Sabit Gider (Kira, Aidat vb.)", "Ev Kredisi Taksiti", "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)"]:
            initial_faizli_tutar = 0.0
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0 
            debt_zorunlu_anapara_yuzdesi = 0.0
            kk_limit = 0.0
            
            with col_f2:
                st.info("Gider Detayları")
                if debt_type == "Ev Kredisi Taksiti":
                    debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=1.0, value=25000.0, key=f'sabit_gider_tutar_{context}')
                    debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=120, key=f'kalan_taksit_ay_ev_{context}')
                elif debt_type == "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)":
                     debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=1.0, value=5000.0, key=f'sabit_gider_taksit_{context}')
                     debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=12, key=f'kalan_taksit_ay_{context}')
                else: # Kira, Aidat vb.
                    debt_taksit = st.number_input("Aylık Gider Tutarı", min_value=1.0, value=15000.0, key=f'sabit_gider_tutar_{context}')
                    debt_kalan_ay = 99999 # Süresiz

            with col_f3:
                st.info("Kapanma Durumu")
                if debt_type == "Ev Kredisi Taksiti":
                    devam_etme_yuzdesi_input = st.number_input("Kredi Bitince Devam Yüzdesi (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f'devam_yuzdesi_{context}') / 100.0
                elif debt_type == "Sabit Taksit Gideri (KK Taksiti, Aidat vb.)":
                    devam_etme_yuzdesi_input = st.number_input("Taksit Bitince Devam Yüzdesi (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f'devam_yuzdesi_taksit_{context}') / 100.0
                else:
                    st.markdown("Süresiz/Devam Eden Gider")
                    devam_etme_yuzdesi_input = 1.0
        
        # --- AYLIK HARCAMA SEPETİ (Kütüphaneden) ---
        elif debt_type == "Aylık Harcama Sepeti (Kütüphaneden)":
            initial_faizli_tutar = 0.0
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0 
            debt_zorunlu_anapara_yuzdesi = 0.0
            kk_limit = 0.0
            debt_kalan_ay = 99999 

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
                 st.info("Harcama Yönlendirmesi (Nakit Kabul Edilir)")
                 st.markdown("Bu harcamalar zorunlu gider olarak bütçenizden düşülür ve süresiz devam eder.")
                 devam_etme_yuzdesi_input = 1.0 
        
        else: 
             with col_f2:
                 st.info("Lütfen Yükümlülük Tipini seçin.")

        st.markdown("---")
        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        
        if submit_button:
            if debt_type.startswith("---"):
                st.error("Lütfen geçerli bir yükümlülük tipi seçiniz.")
                return
            if debt_type == "Aylık Harcama Sepeti (Kütüphaneden)" and not harcama_kalemleri_isim:
                 st.error("Harcama Sepeti için en az bir kalem seçmelisiniz.")
                 return
            if initial_faizli_tutar < 0 or debt_taksit < 0:
                st.error("Borç/Taksit tutarı negatif olamaz.")
                return

            final_debt_name = f"{debt_name} ({harcama_kalemleri_isim})" if debt_type == "Aylık Harcama Sepeti (Kütüphaneden)" else debt_name
            
            add_debt(isim=final_debt_name, faizli_anapara=initial_faizli_tutar, oncelik_str=debt_priority_str, borc_tipi=debt_type, sabit_taksit=debt_taksit, kalan_ay=debt_kalan_ay, faiz_aylik=debt_faiz_aylik, kk_asgari_yuzdesi=debt_kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi=debt_zorunlu_anapara_yuzdesi, kk_limit=kk_limit, devam_etme_yuzdesi=devam_etme_yuzdesi_input)
            st.rerun()


# --- 5. Görüntüleme ve Yönetim Fonksiyonları ---

def display_and_manage_debts(context_key): 
    if st.session_state.borclar:
        st.subheader("📊 Mevcut Borçlar ve Giderler")
        
        display_df = pd.DataFrame(st.session_state.borclar)
        
        cols_to_show = ['isim', 'min_kural', 'tutar', 'sabit_taksit', 'faiz_aylik', 'oncelik', 'kalan_ay']
        display_df_filtered = display_df[[col for col in cols_to_show if col in display_df.columns]]
        
        display_df_filtered.columns = ["Yükümlülük Adı", "Kural", "Kalan Anapara", "Aylık Taksit/Gider", "Aylık Faiz (%)", "Öncelik", "Kalan Ay"]
        
        display_df_filtered['Kalan Anapara'] = display_df_filtered['Kalan Anapara'].apply(format_tl)
        display_df_filtered['Aylık Taksit/Gider'] = display_df_filtered['Aylık Taksit/Gider'].apply(format_tl)
        display_df_filtered['Aylık Faiz (%)'] = (display_df_filtered['Aylık Faiz (%)'].fillna(0.0) * 100).apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(display_df_filtered, column_config={"index": "Index No (Silmek için Seçin)"}, hide_index=False, key=f"current_debts_editor_{context_key}") 

        st.info("Kaldırmak istediğiniz yükümlülüklerin solundaki **index numarasını** seçerek 'Sil' butonuna basın.")
        
        debt_indices_to_delete = st.multiselect("Silinecek Yükümlülüğün Index Numarası", options=display_df.index.tolist(), key=f'debt_delete_select_{context_key}')
        
        if st.button(f"Seçili Yükümlülüğü Sil {context_key}", type="secondary", key=f'delete_button_{context_key}'): 
            if not debt_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz yükümlülüklerin index numarasını seçin.")
                return
            
            st.session_state.borclar = [borc for i, borc in enumerate(st.session_state.borclar) if i not in debt_indices_to_delete]
            st.success(f"{len(debt_indices_to_delete)} adet yükümlülük listeden kaldırıldı.")
            st.rerun()
            
    else:
        st.info("Henüz eklenmiş bir borç veya gider bulunmamaktadır.")

def display_and_manage_incomes(context_key): 
    if st.session_state.gelirler:
        st.subheader("💰 Mevcut Gelir Kaynakları")
        gelir_df = pd.DataFrame(st.session_state.gelirler)
        gelir_df = gelir_df[['isim', 'tutar', 'baslangic_ay', 'artis_yuzdesi', 'tek_seferlik']]
        gelir_df.columns = ["Gelir Adı", "Aylık Tutar", "Başlangıç Ayı", "Artış Yüzdesi", "Tek Seferlik Mi?"]
        gelir_df['Aylık Tutar'] = gelir_df['Aylık Tutar'].apply(format_tl)
        gelir_df['Artış Yüzdesi'] = (gelir_df['Artış Yüzdesi'] * 100).apply(lambda x: f"{x:.2f}%")
        st.dataframe(gelir_df, hide_index=False, key=f"current_incomes_editor_{context_key}") 

        st.info("Kaldırmak istediğiniz gelirlerin solundaki **index numarasını** seçerek 'Sil' butonuna basın.")
        
        income_indices_to_delete = st.multiselect("Silinecek Gelirin Index Numarası", options=gelir_df.index.tolist(), key=f'income_delete_select_{context_key}')
        
        if st.button(f"Seçili Geliri Sil {context_key}", type="secondary", key=f'delete_income_button_{context_key}'):
            if not income_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz gelirlerin index numarasını seçin.")
                return
            
            st.session_state.gelirler = [gelir for i, gelir in enumerate(st.session_state.gelirler) if i not in income_indices_to_delete]
            st.success(f"{len(income_indices_to_delete)} adet gelir listeden kaldırıldı.")
            st.rerun()
    else:
        st.info("Henüz eklenmiş bir gelir kaynağı bulunmamaktadır.")


# --- 6. Borç Simülasyonu Fonksiyonu ---
def simule_borc_planı(borclar_initial, gelirler_initial, manuel_oncelikler, total_birikim_hedefi, birikim_tipi_str, **sim_params):
    
    if not borclar_initial or not gelirler_initial:
        return None

    mevcut_borclar = copy.deepcopy(borclar_initial)
    mevcut_gelirler = copy.deepcopy(gelirler_initial)
    
    # Manuel Öncelikleri Uygula
    if sim_params.get('oncelik_stratejisi') == 'Kullanici':
        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'] and borc['isim'] in manuel_oncelikler:
                borc['oncelik'] = manuel_oncelikler[borc['isim']]
    
    ay_sayisi = 0
    mevcut_birikim = sim_params.get('baslangic_birikim', 0.0)
    birikime_ayrilan = sim_params.get('aylik_zorunlu_birikim', 0.0)
    faiz_carpani = sim_params.get('faiz_carpani', 1.0)
    agresiflik_carpan = sim_params.get('agresiflik_carpan', 1.0)
    birikim_artis_aylik = sim_params.get('birikim_artis_aylik', 0.0) / 12 / 100
    
    toplam_faiz_maliyeti = 0.0
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    
    aylik_sonuclar = []
    
    limit_asimi = False
    
    while True:
        ay_sayisi += 1
        ay_adi = f"Ay {ay_sayisi}"
        
        # --- Bitiş Kontrolleri ---
        borc_tamamlandi = not any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
        
        # Birikim Hedefi Kontrolü
        if sim_params.get('birikim_tipi_str') == "Borç Bitimine Kadar Toplam Tutar":
            birikim_hedefi_tamamlandi = mevcut_birikim >= sim_params.get('total_birikim_hedefi', 0)
        else:
            birikim_hedefi_tamamlandi = True

        if ay_sayisi > 1 and borc_tamamlandi and birikim_hedefi_tamamlandi:
            break
        
        if ay_sayisi > 360:
            limit_asimi = True
            break
        
        # --- Gelir Hesaplama ---
        toplam_gelir = 0.0
        for gelir in mevcut_gelirler:
            if ay_sayisi >= gelir['baslangic_ay']:
                if gelir['tek_seferlik']:
                    if ay_sayisi == gelir['baslangic_ay']:
                        toplam_gelir += gelir['tutar']
                else:
                    artis_carpan = (1 + gelir['artis_yuzdesi']) ** ((ay_sayisi - gelir['baslangic_ay']) / 12)
                    toplam_gelir += gelir['tutar'] * artis_carpan

        # --- Giderlerin Kapanması ve Yeniden Atanması ---
        
        zorunlu_gider_toplam = birikime_ayrilan
        min_borc_odeme_toplam = 0.0
        
        aktif_borclar_sonraki_ay = []
        serbest_kalan_nakit_bu_ay = 0.0
        kapanan_giderler_listesi = []

        for borc in mevcut_borclar:
            is_sureli_gider = borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'] and borc.get('kalan_ay', 99999) < 99999
            
            if is_sureli_gider:
                if borc['kalan_ay'] == 1:
                    odenen_miktar = borc.get('sabit_taksit', 0)
                    devam_yuzdesi = borc.get('devam_etme_yuzdesi', 0.0)
                    serbest_kalan_nakit_bu_ay += odenen_miktar * (1 - devam_yuzdesi)
                    devam_eden_miktar = odenen_miktar * devam_yuzdesi
                    
                    if devam_eden_miktar > 0:
                        yeni_gider = {"isim": f"Serbest Kalan Harcama ({borc['isim']})", "tutar": 0, "min_kural": "SABIT_GIDER", "oncelik": 1, "sabit_taksit": devam_eden_miktar, "kalan_ay": 99999, "faiz_aylik": 0, "kk_asgari_yuzdesi": 0, "limit": 0, "zorunlu_anapara_yuzdesi": 0, "devam_etme_yuzdesi": 1.0}
                        aktif_borclar_sonraki_ay.append(yeni_gider)
                        
                    kapanan_giderler_listesi.append(borc['isim'])
                else:
                    borc['kalan_ay'] -= 1
                    aktif_borclar_sonraki_ay.append(borc)
            else:
                aktif_borclar_sonraki_ay.append(borc)
                
        mevcut_borclar = aktif_borclar_sonraki_ay
        
        # --- Minimum Ödeme Hesaplama (Giderler ve Borçlar) ---
        for borc in mevcut_borclar:
            min_odeme = hesapla_min_odeme(borc, faiz_carpani)
            if borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                zorunlu_gider_toplam += min_odeme
            else:
                min_borc_odeme_toplam += min_odeme

        # --- Saldırı Gücü Hesaplama ---
        if ay_sayisi == 1:
            ilk_ay_toplam_gelir = toplam_gelir
            ilk_ay_toplam_gider = zorunlu_gider_toplam + min_borc_odeme_toplam

        kalan_nakit = toplam_gelir - zorunlu_gider_toplam - min_borc_odeme_toplam
        saldırı_gucu = max(0, kalan_nakit * agresiflik_carpan)
        saldırı_gucu += serbest_kalan_nakit_bu_ay 

        # --- Faiz Ekleme ve Minimum Ödeme Çıkarma ---
        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                if borc['tutar'] > 1:
                    etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                    eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani
                    toplam_faiz_maliyeti += eklenen_faiz
                    borc['tutar'] += eklenen_faiz
                    borc['tutar'] -= hesapla_min_odeme(borc, faiz_carpani)
        
        # --- Ek Ödeme / Borç Saldırısı ---
        saldırı_kalan = saldırı_gucu
        
        if sim_params['oncelik_stratejisi'] == 'Avalanche':
            mevcut_borclar.sort(key=lambda x: (x.get('faiz_aylik', 0), x.get('tutar', 0)), reverse=True)
        elif sim_params['oncelik_stratejisi'] == 'Snowball':
            mevcut_borclar.sort(key=lambda x: x.get('tutar', float('inf')) if x.get('tutar', 0) > 1 else float('inf'))
        else:
            mevcut_borclar.sort(key=lambda x: x.get('oncelik', float('inf')))

        kapanan_borclar_listesi = []
        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                if borc['tutar'] > 1 and saldırı_kalan > 0:
                    odecek_tutar = min(saldırı_kalan, borc['tutar'])
                    borc['tutar'] -= odecek_tutar
                    saldırı_kalan -= odecek_tutar
                    if borc['tutar'] <= 1:
                        kapanan_borclar_listesi.append(borc['isim'])
                        borc['tutar'] = 0
        
        # --- Birikim Güncelleme ---
        mevcut_birikim += saldırı_kalan 
        mevcut_birikim *= (1 + birikim_artis_aylik)

        aylik_sonuclar.append({
            'Ay': ay_adi, 'Toplam Gelir': round(toplam_gelir), 'Toplam Zorunlu Giderler': round(zorunlu_gider_toplam), 'Min. Borç Ödemeleri': round(min_borc_odeme_toplam), 'Ek Ödeme Gücü': round(saldırı_gucu), 'Aylık Birikim Katkısı': round(birikime_ayrilan + saldırı_kalan + serbest_kalan_nakit_bu_ay), 'Kapanan Borçlar/Giderler': ", ".join(kapanan_borclar_listesi + kapanan_giderler_listesi) if kapanan_borclar_listesi or kapanan_giderler_listesi else '-', 'Kalan Faizli Borç Toplamı': round(sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])), 'Toplam Birikim': round(mevcut_birikim)
        })

    return {"df": pd.DataFrame(aylik_sonuclar), "ay_sayisi": ay_sayisi, "toplam_faiz": round(toplam_faiz_maliyeti), "toplam_birikim": round(mevcut_birikim), "baslangic_faizli_borc": round(baslangic_faizli_borc), "ilk_ay_gelir": ilk_ay_toplam_gelir if 'ilk_ay_toplam_gelir' in locals() else 0, "ilk_ay_gider": ilk_ay_toplam_gider if 'ilk_ay_toplam_gider' in locals() else 0, "limit_asimi": limit_asimi}

# --- YENİ RAPORLAMA VE TAVSİYE FONKSİYONLARI ---

def run_alternative_scenario(borclar, gelirler, current_params, new_strategy_name, new_agresiflik_name):
    """Farklı bir stratejiyle simülasyonu çalıştırır."""
    
    agresiflik_carpan = STRATEJILER[new_agresiflik_name]
    oncelik_stratejisi = ONCELIK_STRATEJILERI.get(new_strategy_name, current_params['oncelik_stratejisi'])
    
    sim_params = copy.deepcopy(current_params)
    sim_params.update({
        'agresiflik_carpan': agresiflik_carpan,
        'oncelik_stratejisi': oncelik_stratejisi
    })
    
    # HATA GİDERME: total_birikim_hedefi ve birikim_tipi_str'yi sim_params'tan çekerek pasla
    total_birikim_hedefi = sim_params.get('total_birikim_hedefi', 0.0)
    birikim_tipi_str = sim_params.get('birikim_tipi_str', 'Aylık Sabit Tutar')
    
    sonuc = simule_borc_planı(borclar, gelirler, {}, total_birikim_hedefi, birikim_tipi_str, **sim_params)
    
    return {
        'isim': f"{new_strategy_name} ({new_agresiflik_name})",
        'ay_sayisi': sonuc['ay_sayisi'],
        'toplam_faiz': sonuc['toplam_faiz'],
        'toplam_birikim': sonuc['toplam_birikim']
    }

def generate_report_and_recommendations(sonuc, current_params):
    
    # 1. Alternatif Senaryoların Çalıştırılması
    alternatifler = []
    
    # Güvenli Strateji ve Agresiflik Adı Çekimi
    current_strat_list = [k for k, v in ONCELIK_STRATEJILERI.items() if v == current_params['oncelik_stratejisi']]
    current_strat = current_strat_list[0] if current_strat_list else "Kullanıcı Tanımlı Sıra"
    is_avalanche = current_strat.startswith("Borç Çığı")
    
    current_agresiflik_val = current_params['agresiflik_carpan']
    current_agresiflik_name_list = [k for k, v in STRATEJILER.items() if v == current_agresiflik_val]
    current_agresiflik_name = current_agresiflik_name_list[0] if current_agresiflik_name_list else "Maksimum Çaba (Tüm Ek Ödeme)"

    # a) Öncelik Tersine Çevirme (Avalanche vs Snowball)
    if current_strat == "Kullanıcı Tanımlı Sıra":
        alt_strat_name = "Borç Çığı (Avalanche - Önce Faiz)" 
    elif is_avalanche:
        alt_strat_name = "Borç Kartopu (Snowball - Önce Tutar)"
    else:
        alt_strat_name = "Borç Çığı (Avalanche - Önce Faiz)"
        
    try:
        if current_strat != alt_strat_name: 
            alternatifler.append(run_alternative_scenario(st.session_state.borclar, st.session_state.gelirler, current_params, alt_strat_name, current_agresiflik_name))
    except: pass
        
    # b) Agresiflik Değiştirme (Maksimum Çaba vs. Temkinli/Aşırı Çaba)
    alt_agresiflik_name = ""
    
    if current_agresiflik_val == STRATEJILER["Maksimum Çaba (Tüm Ek Ödeme)"]:
        alt_agresiflik_name = "Temkinli (Yüzde 50)"
    elif current_agresiflik_val <= STRATEJILER["Temkinli (Yüzde 50)"]:
        alt_agresiflik_name = "Maksimum Çaba (Tüm Ek Ödeme)"
        
    if alt_agresiflik_name and alt_agresiflik_name != current_agresiflik_name:
        try:
            alternatifler.append(run_alternative_scenario(st.session_state.borclar, st.session_state.gelirler, current_params, current_strat, alt_agresiflik_name))
        except: pass
    
    # 2. Tavsiye Oluşturma
    tavsiyeler = []
    
    if sonuc['limit_asimi']:
        tavsiyeler.append("🚨 **ACİL DURUM:** Simülasyon süresi 30 yılı aştı! Mevcut gelir ve gider yapınızla borçlarınızı kapatmanız mümkün görünmüyor. **Gelir artışı veya sabit giderlerde ciddi kesintiler** yapmayı düşünün.")
    elif sonuc['ay_sayisi'] <= 12:
        tavsiyeler.append("✅ **TEBRİKLER!** Borçlarınızı bir yıldan kısa sürede kapatıyorsunuz. Finansal olarak çok iyi bir yoldasınız.")
    
    
    # Senaryo Karşılaştırma Tavsiyeleri
    for alt in alternatifler:
        faiz_farki = sonuc['toplam_faiz'] - alt['toplam_faiz']
        süre_farki = sonuc['ay_sayisi'] - alt['ay_sayisi']
        
        if faiz_farki > 0 and süre_farki >= 0:
            tavsiyeler.append(f"💰 **DAHA UCUZ/HIZLI FIRSAT:** '{alt['isim'].split('(')[0].strip()}' stratejisini uygularsanız, borç sürenizi **{süre_farki} ay** kısaltabilir ve **{format_tl(faiz_farki)}** ek faiz tasarrufu sağlayabilirsiniz.")
        elif süre_farki > 0 and faiz_farki > -(sonuc['toplam_faiz'] * 0.05):
             tavsiyeler.append(f"⏱️ **MOTİVASYON KAZANCI:** '{alt['isim'].split('(')[0].strip()}' stratejisi ile borçlarınızı **{süre_farki} ay** daha erken kapatabilirsiniz. Bu, motivasyonunuzu artırabilir!")

    # 3. Excel İndirme İçin DataFrame Hazırlığı
    excel_data = io.BytesIO()
    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
        sonuc['df'].to_excel(writer, index=False, sheet_name='Aylık Finansal Akış')
        
    excel_data.seek(0)
    
    return {"alternatifler": alternatifler, "tavsiyeler": tavsiyeler, "excel_data": excel_data}


# --- 7. Ana Uygulama Düzeni ---
st.title("Borç Kapatma ve Finansal Planlama Simülasyonu")

# --- KRİTİK ALAN: YÜKLEME VE KAYDETME ---
st.header("🗂️ Profil Yönetimi (Yerel Kayıt)")
col_load, col_save = st.columns(2)

# YÜKLEME ALANI
with col_load:
    uploaded_file = st.file_uploader("Yedekleme Dosyasını (JSON) Yükle", type=['json'], key="file_uploader_main")
    if uploaded_file:
        load_data_from_upload(uploaded_file)
        
# KAYDETME/İNDİRME ALANI
with col_save:
    st.markdown(" ")
    data_to_save = create_save_data()
    st.download_button(
        label="💾 Mevcut Verileri İndir (Yedekleme)",
        data=data_to_save,
        file_name=f"finans_plan_yedekleme_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        help="Mevcut tüm gelir/gider/kural verilerini JSON dosyası olarak PC'nize indirir."
    )
st.markdown("---")
# --- SON KRİTİK ALAN ---


tab_basic, tab_advanced, tab_rules = st.tabs(["✨ Basit Planlama (Başlangıç)", "🚀 Gelişmiş Planlama", "⚙️ Yönetici Kuralları"])

# --- TAB 2: Basit Planlama ---
with tab_basic:
    st.header("✨ Hızlı ve Varsayılan Planlama")
    
    col_st1, col_st2 = st.columns(2)
    with col_st1:
        BIRIKIM_TIPI_BASIC = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_basic')
        AYLIK_ZORUNLU_BIRIKIM_BASIC = st.number_input("Aylık Zorunlu Birikim Tutarı", value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik_basic', disabled=BIRIKIM_TIPI_BASIC != "Aylık Sabit Tutar")
        TOPLAM_BIRIKIM_HEDEFI_BASIC = st.number_input("Hedef Toplam Birikim Tutarı", value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam_basic', disabled=BIRIKIM_TIPI_BASIC != "Borç Bitimine Kadar Toplam Tutar")
        BASLANGIC_BIRIKIM_BASIC = st.number_input("Mevcut Başlangıç Birikimi", value=0, step=1000, min_value=0, key='baslangic_birikim_basic')
    with col_st2:
        st.markdown(f"**Borç Kapatma Yöntemi:** **{st.session_state.get('default_oncelik', 'Borç Çığı (Avalanche - Önce Faiz)')}**")
        st.markdown(f"**Ek Ödeme Agresifliği:** **{st.session_state.get('default_agressiflik', 'Maksimum Çaba (Tüm Ek Ödeme)')}**")
        st.markdown(f"**Birikim Değerlemesi:** TL Mevduat (Yıllık **%{st.session_state.get('default_aylik_artis', 3.5)}** Artış)")

    st.markdown("---")
    render_income_form("basic")
    st.markdown("---")
    render_debt_form("basic")

    st.markdown("---")
    display_and_manage_incomes("basic")
    display_and_manage_debts("basic")
    
    st.markdown("---")
    is_disabled_basic = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_basic = st.button("BORÇ KAPATMA PLANINI OLUŞTUR", type="primary", disabled=is_disabled_basic, key="calc_basic")


# --- TAB 1: Gelişmiş Planlama ---
with tab_advanced:
    st.header("🚀 Gelişmiş Planlama ve Senaryo Yönetimi")
    
    col_st1, col_st2, col_st3 = st.columns(3)
    with col_st1:
        AGRESIFLIK_ADVANCED = st.selectbox("Ek Ödeme Agresifliği", options=list(STRATEJILER.keys()), index=2, key='agresiflik_adv')
        ONCELIK_ADVANCED = st.selectbox("Borç Kapatma Yöntemi", options=list(ONCELIK_STRATEJILERI.keys()), index=0, key='oncelik_adv')
    
    with col_st2:
        FAIZ_CARPANI_ADVANCED = st.slider("Faiz Oranı Çarpanı", min_value=0.5, max_value=2.0, value=1.0, step=0.1, key='faiz_carpan_adv')
        with st.expander("❓ Faiz Çarpanı Ne İşe Yarar?"):
            st.markdown("Bu çarpan, girdiğiniz tüm faiz oranlarını test amaçlı artırmanıza veya azaltmanıza olanak tanır.")
        AYLIK_ARTIS_ADVANCED = st.number_input("Birikim Yıllık Artış Yüzdesi (%)", value=3.5, min_value=0.0, step=0.1, key='aylik_artis_adv')
        
    with col_st3:
        BIRIKIM_TIPI_ADVANCED = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_adv')
        AYLIK_ZORUNLU_BIRIKIM_ADVANCED = st.number_input("Aylık Zorunlu Birikim Tutarı", value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik_adv', disabled=BIRIKIM_TIPI_ADVANCED != "Aylık Sabit Tutar")
        TOPLAM_BIRIKIM_HEDEFI_ADVANCED = st.number_input("Hedef Toplam Birikim Tutarı", value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam_adv', disabled=BIRIKIM_TIPI_ADVANCED != "Borç Bitimine Kadar Toplam Tutar")
        BASLANGIC_BIRIKIM_ADVANCED = st.number_input("Mevcut Başlangıç Birikimi", value=0, step=1000, min_value=0, key='baslangic_birikim_adv')


    st.markdown("---")
    render_income_form("advanced")
    st.markdown("---")
    render_debt_form("advanced")
    
    # Manuel Borç Sıralaması Editörü
    st.markdown("---")
    st.subheader("🛠️ Manuel Borç Kapatma Sırası (Gelişmiş)")
    if ONCELIK_ADVANCED == "Kullanıcı Tanımlı Sıra":
        if st.session_state.borclar:
            odemeye_acik_borclar = [b for b in st.session_state.borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']]
            if odemeye_acik_borclar:
                siralama_df = pd.DataFrame([{'isim': b['isim'], 'mevcut_oncelik': b['oncelik'] - 1000 if b['oncelik'] > 999 else b['oncelik'], 'yeni_oncelik': st.session_state.manuel_oncelik_listesi.get(b['isim'], b['oncelik']) - 1000 if st.session_state.manuel_oncelik_listesi.get(b['isim'], b['oncelik']) > 999 else st.session_state.manuel_oncelik_listesi.get(b['isim'], b['oncelik'])} for b in odemeye_acik_borclar])
                siralama_df = siralama_df.sort_values(by='yeni_oncelik', ascending=True)
                st.info("Borç önceliklerini manuel olarak ayarlamak için **'Yeni Öncelik'** sütunundaki numaraları değiştirin.")
                edited_siralama_df = st.data_editor(siralama_df, column_config={"yeni_oncelik": st.column_config.NumberColumn("Yeni Öncelik", min_value=1, step=1), "isim": st.column_config.TextColumn("Borç Adı", disabled=True), "mevcut_oncelik": st.column_config.TextColumn("Mevcut Sıra", disabled=True)}, hide_index=True, key='advanced_priority_editor')
                st.session_state.manuel_oncelik_listesi = edited_siralama_df.set_index('isim')['yeni_oncelik'].apply(lambda x: x + 1000).to_dict()
            else:
                st.info("Ek ödemeye açık borç (KK, KMH, Kredi) bulunmamaktadır.")
        else:
            st.warning("Lütfen önce borç yükümlülüklerini ekleyin.")
    else:
        st.info("Manuel sıralama, sadece **'Borç Kapatma Yöntemi'** **Kullanıcı Tanımlı Sıra** olarak seçildiğinde geçerlidir.")

    st.markdown("---")
    display_and_manage_incomes("advanced")
    display_and_manage_debts("advanced")
    
    st.markdown("---")
    is_disabled_advanced = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_advanced = st.button("GELİŞMİŞ PLAN OLUŞTUR", type="primary", disabled=is_disabled_advanced, key="calc_adv")


# --- TAB 3: Yönetici Kuralları ---
with tab_rules:
    st.header("Simülasyon Kurallarını Yönet")
    
    st.subheader("Basit Planlama Varsayılanlarını Ayarla")
    st.session_state['default_agresiflik'] = st.selectbox("Varsayılan Ek Ödeme Agresifliği", options=list(STRATEJILER.keys()), index=2, key='default_agressiflik_rule')
    st.session_state['default_oncelik'] = st.selectbox("Varsayılan Borç Kapatma Yöntemi", options=list(ONCELIK_STRATEJILERI.keys()), index=0, key='default_oncelik_rule')
    st.session_state['default_aylik_artis'] = st.number_input("Varsayılan Birikim Yıllık Artışı (%)", value=3.5, min_value=0.0, step=0.1, key='default_aylik_artis_rule')
    
    st.markdown("---")
    st.subheader("🇹🇷 BDDK ve Yasal Limitler (Türkiye)")
    st.warning("Kredi Kartı Dönem Borcu hesaplamaları bu değerleri kullanır.")
    
    col_l1, col_l2, col_l3 = st.columns(3)
    
    with col_l1:
        st.session_state.tr_params['kk_taksit_max_ay'] = st.number_input("KK Mal/Hizmet Max Taksit Ayı", min_value=1, value=st.session_state.tr_params['kk_taksit_max_ay'], step=1, key='bddk_kk_taksit_max')
        st.session_state.tr_params['kk_aylik_akdi_faiz'] = st.number_input("KK Aylık Akdi Faiz (%) (Dönem Borcu)", min_value=0.0, value=st.session_state.tr_params['kk_aylik_akdi_faiz'], step=0.01, key='bddk_kk_faiz')
        
    with col_l2:
        st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] = st.number_input("KK Asgari Ödeme Yüzdesi (%) (Dönem Borcu)", min_value=0.0, max_value=100.0, value=st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'], step=1.0, key='bddk_kk_asgari_yuzde')
        st.session_state.tr_params['kk_aylik_gecikme_faiz'] = st.number_input("KK Aylık Gecikme Faiz (%)", min_value=0.0, value=st.session_state.tr_params['kk_aylik_gecikme_faiz'], step=0.01, key='bddk_kk_gecikme')
        
    with col_l3:
        st.session_state.tr_params['kredi_taksit_max_ay'] = st.number_input("İhtiyaç Kredisi Max Taksit Ayı", min_value=1, value=st.session_state.tr_params['kredi_taksit_max_ay'], step=1, key='bddk_kredi_max')
        st.session_state.tr_params['kmh_aylik_faiz'] = st.number_input("KMH/Kredi Piyasa Faizi (%) (Max)", min_value=0.0, value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.1, key='bddk_kmh_faiz')
        
    st.markdown("---")
    st.subheader("💳 Aylık Harcama Kalemleri Kütüphanesi")
    
    edited_df = st.data_editor(st.session_state.harcama_kalemleri_df, column_config={"Kalem Adı": st.column_config.TextColumn("Kalem Adı", required=True), "Aylık Bütçe (TL)": st.column_config.NumberColumn("Aylık Bütçe (TL)", min_value=0, step=100, format="%.0f TL")}, num_rows="dynamic", hide_index=True, key='harcama_editor')
    st.session_state.harcama_kalemleri_df = edited_df

    toplam_butce = st.session_state.harcama_kalemleri_df['Aylık Bütçe (TL)'].sum()
    st.markdown(f"**Tanımlanan Toplam Aylık Bütçe:** **{int(toplam_butce):,} TL**")
    st.markdown("---")


# --- 8. Hesaplama Tetikleyicileri ---

if calculate_button_advanced or calculate_button_basic:
    
    # --- 1. Parametreleri Hazırla ---
    if calculate_button_advanced:
        total_birikim_hedefi = TOPLAM_BIRIKIM_HEDEFI_ADVANCED
        birikim_tipi_str = BIRIKIM_TIPI_ADVANCED
        manuel_oncelikler = st.session_state.manuel_oncelik_listesi
        sim_params = {'agresiflik_carpan': STRATEJILER[AGRESIFLIK_ADVANCED], 'oncelik_stratejisi': ONCELIK_STRATEJILERI[ONCELIK_ADVANCED], 'faiz_carpani': FAIZ_CARPANI_ADVANCED, 'birikim_artis_aylik': AYLIK_ARTIS_ADVANCED, 'aylik_zorunlu_birikim': AYLIK_ZORUNLU_BIRIKIM_ADVANCED if BIRIKIM_TIPI_ADVANCED == "Aylık Sabit Tutar" else 0, 'baslangic_birikim': BASLANGIC_BIRIKIM_ADVANCED}
    else: # Basit Planlama
        varsayilan_agresiflik_str = st.session_state.get('default_agressiflik', 'Maksimum Çaba (Tüm Ek Ödeme)')
        varsayilan_oncelik_str = st.session_state.get('default_oncelik', 'Borç Çığı (Avalanche - Önce Faiz)')
        total_birikim_hedefi = TOPLAM_BIRIKIM_HEDEFI_BASIC
        birikim_tipi_str = BIRIKIM_TIPI_BASIC
        manuel_oncelikler = {}
        sim_params = {'agresiflik_carpan': STRATEJILER[varsayilan_agresiflik_str], 'oncelik_stratejisi': ONCELIK_STRATEJILERI[varsayilan_oncelik_str], 'faiz_carpani': 1.0, 'birikim_artis_aylik': st.session_state.get('default_aylik_artis', 3.5), 'aylik_zorunlu_birikim': AYLIK_ZORUNLU_BIRIKIM_BASIC if BIRIKIM_TIPI_BASIC == "Aylık Sabit Tutar" else 0, 'baslangic_birikim': BASLANGIC_BIRIKIM_BASIC}
    
    # KRİTİK DÜZELTME: Zorunlu parametreleri sim_params içine ekle
    sim_params['total_birikim_hedefi'] = total_birikim_hedefi
    sim_params['birikim_tipi_str'] = birikim_tipi_str


    # Ana Simülasyonu Çalıştır
    sonuc = simule_borc_planı(st.session_state.borclar, st.session_state.gelirler, manuel_oncelikler, total_birikim_hedefi, birikim_tipi_str, **sim_params)

    if sonuc:
        
        # Raporları ve Tavsiyeleri Oluştur
        rapor_sonuclari = generate_report_and_recommendations(sonuc, sim_params)
        
        with st.container():
            st.markdown("---")
            st.header("🏆 Borç Yönetimi Karşılaştırmalı Raporu")
            
            if sonuc.get('limit_asimi'): st.error("‼️ Simülasyon 30 yılı aştığı için durduruldu. Borçlarınızı bu planla kapatmanız mümkün görünmüyor.")
            else: st.success("✅ Simülasyon başarıyla tamamlandı!")
            
            
            # --- ÖZET VE TAVSİYELER ---
            st.subheader("💡 Kişiselleştirilmiş Tavsiyeler ve Analiz")
            for tavsiye in rapor_sonuclari['tavsiyeler']:
                st.markdown(tavsiye)
                
            st.markdown("---")
            
            # --- SENARYO KARŞILAŞTIRMA TABLOSU ---
            ozet_data = [{'Senaryo': 'Mevcut Plan (Seçiminiz)', 'Süre': sonuc['ay_sayisi'], 'Faiz Maliyeti': sonuc['toplam_faiz'], 'Kapanış Birikimi': sonuc['toplam_birikim']}]
            for alt in rapor_sonuclari['alternatifler']:
                 ozet_data.append({'Senaryo': alt['isim'], 'Süre': alt['ay_sayisi'], 'Faiz Maliyeti': alt['toplam_faiz'], 'Kapanış Birikimi': alt['toplam_birikim']})
            
            ozet_df = pd.DataFrame(ozet_data)
            
            # Veri formatlama
            ozet_df['Süre'] = ozet_df['Süre'].apply(lambda x: f"{x // 12} Yıl {x % 12} Ay")
            ozet_df['Faiz Maliyeti'] = ozet_df['Faiz Maliyeti'].apply(format_tl)
            ozet_df['Kapanış Birikimi'] = ozet_df['Kapanış Birikimi'].apply(format_tl)
            
            st.subheader("📊 Senaryo Karşılaştırma Özeti")
            st.dataframe(ozet_df, hide_index=True)
            
            # --- DETAYLI TABLO VE EXCEL İNDİRME ---
            st.subheader("📋 Aylık Simülasyon Detayları")
            
            col_res1, col_res2 = st.columns([3, 1])
            with col_res2:
                 st.download_button(
                    label="⬇️ Excel İndir (Tüm Detaylar)",
                    data=rapor_sonuclari['excel_data'],
                    file_name=f"Borc_Simulasyon_Detay_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col_res1:
                st.dataframe(sonuc['df'], hide_index=True)
