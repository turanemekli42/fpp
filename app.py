import streamlit as st
import pandas as pd
import numpy as np
import copy

# --- 0. Yapılandırma ---
st.set_page_config(
    page_title="Borç Yönetimi Simülasyonu",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- 1. Sabitler ve Kurallar (Güncel Kelimeler Kullanıldı) ---

STRATEJILER = {
    "Minimum Çaba (Minimum Ek Ödeme)": 0.0,
    "Temkinli (Yüzde 50)": 0.5,
    "Maksimum Çaba (Tüm Ek Ödeme)": 1.0, # ESKİSİ: Saldırgan
    "Aşırı Çaba (x1.5 Ek Ödeme)": 1.5,   # ESKİSİ: Ultra Agresif
}

ONCELIK_STRATEJILERI = {
    "Borç Çığı (Avalanche - Önce Faiz)": "Avalanche",
    "Borç Kartopu (Snowball - Önce Tutar)": "Snowball",
    "Kullanıcı Tanımlı Sıra": "Kullanici"
}

# Para formatlama fonksiyonu
def format_tl(tutar):
    # NaN kontrolü ekleyelim
    if pd.isna(tutar) or tutar is None:
        return "0 TL"
    return f"{int(tutar):,} TL"

# --- 2. Session State Başlatma ---

if 'borclar' not in st.session_state:
    st.session_state.borclar = []
if 'gelirler' not in st.session_state:
    st.session_state.gelirler = []
if 'tek_seferlik_gelir_isaretleyicisi' not in st.session_state:
    st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

# Harcama Kütüphanesi Başlangıç Değerleri
if 'harcama_kalemleri_df' not in st.session_state:
    st.session_state.harcama_kalemleri_df = pd.DataFrame({
        'Kalem Adı': ['Market', 'Ulaşım', 'Eğlence', 'Kişisel Bakım'],
        'Aylık Bütçe (TL)': [15000, 3000, 2000, 1500]
    })
if 'manuel_oncelik_listesi' not in st.session_state:
    st.session_state.manuel_oncelik_listesi = {}

# Türkiye Yasal Parametreleri (BDDK/Merkez Bankası)
if 'tr_params' not in st.session_state:
    st.session_state.tr_params = {
        'kk_taksit_max_ay': 12,
        'kk_asgari_odeme_yuzdesi_default': 20.0,
        'kk_aylik_akdi_faiz': 3.66,
        'kk_aylik_gecikme_faiz': 3.96,
        'kmh_aylik_faiz': 5.0,
        'kredi_taksit_max_ay': 36,
    }


# --- 3. Yardımcı Fonksiyonlar ---

def hesapla_min_odeme(borc, faiz_carpani=1.0):
    kural = borc.get('min_kural')
    tutar = borc.get('tutar', 0)
    
    if kural in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
        return borc.get('sabit_taksit', 0)
    
    elif kural == 'SABIT_TAKSIT_ANAPARA':
        # Kredi Taksiti (Faiz dahil sabit taksiti zorunlu ödeme kabul ediyoruz)
        return borc.get('sabit_taksit', 0)
    
    elif kural == 'ASGARI_FAIZ': # Kredi Kartı
        asgari_anapara_yuzdesi = borc.get('kk_asgari_yuzdesi', 0)
        return tutar * asgari_anapara_yuzdesi
    
    elif kural in ['FAIZ_ART_ANAPARA', 'FAIZ']: # KMH ve Diğer Faizli
        zorunlu_anapara_yuzdesi = borc.get('zorunlu_anapara_yuzdesi', 0)
        return tutar * zorunlu_anapara_yuzdesi
    
    return 0


def add_debt(isim, faizli_anapara, oncelik_str, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi, kk_limit=0.0, devam_etme_yuzdesi=0.0):
    
    borc_listesi = []
    final_priority = 1

    if oncelik_str:
        priority_val = int(oncelik_str.split('.')[0])
        final_priority = priority_val + 1000

    # 2. Borç Objektlerini Oluşturma
    
    if borc_tipi == "Sabit Gider (Harcama Sepeti)" or borc_tipi in ["Sabit Kira Gideri", "Ev Kredisi Taksiti"]:
        kural_type = "SABIT_GIDER"
        
        borc_listesi.append({
            "isim": isim,
            "tutar": 0, "min_kural": kural_type,
            "oncelik": 1, "sabit_taksit": sabit_taksit,
            "kalan_ay": kalan_ay if borc_tipi != "Sabit Kira Gideri" else 99999,
            "faiz_aylik": 0, "kk_asgari_yuzdesi": 0,
            "limit": 0, "devam_etme_yuzdesi": devam_etme_yuzdesi
        })
    
    elif borc_tipi == "Kredi Kartı":
        # 1. KK Taksitli Alışverişler (Sabit Gider)
        if sabit_taksit > 0 and kalan_ay > 0:
            borc_listesi.append({
                "isim": f"{isim} (Taksitler)",
                "tutar": sabit_taksit * kalan_ay, "min_kural": "SABIT_TAKSIT_GIDER",
                "oncelik": 1, "sabit_taksit": sabit_taksit,
                "kalan_ay": kalan_ay, "faiz_aylik": 0, "kk_asgari_yuzdesi": 0,
                "limit": kk_limit, "devam_etme_yuzdesi": 0.0
            })
        
        # 2. KK Dönem Borcu (Faizli Borç)
        if faizli_anapara > 0:
             borc_listesi.append({
                "isim": f"{isim} (Dönem Borcu)",
                "tutar": faizli_anapara, "min_kural": "ASGARI_FAIZ",
                "oncelik": final_priority,
                "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
                "kalan_ay": 99999,
                "limit": kk_limit, "devam_etme_yuzdesi": 0.0
            })
    
    elif borc_tipi == "Ek Hesap (KMH)":
        borc_listesi.append({
            "isim": isim,
            "tutar": faizli_anapara, "min_kural": "FAIZ_ART_ANAPARA",
            "oncelik": final_priority,
            "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0.0,
            "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi,
            "kalan_ay": 99999,
            "limit": kk_limit, "devam_etme_yuzdesi": 0.0
        })

    elif borc_tipi == "Kredi (Sabit Taksit)":
        borc_listesi.append({
            "isim": isim,
            "tutar": faizli_anapara, "min_kural": "SABIT_TAKSIT_ANAPARA",
            "oncelik": final_priority,
            "sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay,
            "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0,
            "limit": 0, "devam_etme_yuzdesi": 0.0
        })
        
    elif borc_tipi == "Diğer Faizli Borç":
        borc_listesi.append({
            "isim": isim,
            "tutar": faizli_anapara, "min_kural": "FAIZ",
            "oncelik": final_priority,
            "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0,
            "kalan_ay": 99999,
            "limit": 0, "devam_etme_yuzdesi": 0.0
        })

    
    if borc_listesi:
        st.session_state.borclar.extend(borc_listesi)
        st.success(f"'{isim}' borcu/gideri başarıyla eklendi.")


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


def render_debt_form(context):
    st.subheader(f"Borçları ve Giderleri Yönet ({context})") # Yükümlülük -> Borç ve Gider
    
    kk_limit = 0.0
    kmh_limit = 0.0
    harcama_kalemleri_isim = ""

    with st.form(f"new_debt_form_{context}", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns(3)
        
        # --- COL F1: Temel Bilgiler ---
        with col_f1:
            debt_name = st.text_input("Borç/Gider Adı", value="Yeni Borç", key=f'debt_name_{context}')
            
            debt_type = st.selectbox("Yükümlülük Tipi",
                                     ["Kredi Kartı", "Ek Hesap (KMH)",
                                      "--- Sabit Giderler ---",
                                      "Sabit Kira Gideri", "Ev Kredisi Taksiti",
                                      "--- Aylık Harcamalar ---",
                                      "Aylık Harcama Sepeti (Kütüphaneden)",
                                      "--- Sabit Ödemeli Borçlar ---",
                                      "Kredi (Sabit Taksit)",
                                      "--- Diğer Faizli Borçlar ---",
                                      "Diğer Faizli Borç"], key=f'debt_type_{context}')
            
            # --- Mantık Değişkenleri ---
            is_faizli_borc_ve_ek_odemeli = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Kredi (Sabit Taksit)", "Diğer Faizli Borç"]
            is_faizli_borc = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Diğer Faizli Borç"]
            is_sabit_gider = debt_type in ["Sabit Kira Gideri", "Ev Kredisi Taksiti"]
            is_sabit_kredi = debt_type == "Kredi (Sabit Taksit)"
            is_kk = debt_type == "Kredi Kartı"
            is_kmh = debt_type == "Ek Hesap (KMH)"
            is_harcama_sepeti = debt_type == "Aylık Harcama Sepeti (Kütüphaneden)"
            
            # ÖNCELİK MANTIK BLOĞU
            debt_priority_str = ""
            if is_faizli_borc_ve_ek_odemeli:
                ek_odemeye_acik_borclar_info = [
                    (b['isim'], b['oncelik']) for b in st.session_state.borclar
                    if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
                ]
                
                ek_odemeye_acik_borclar_info.sort(key=lambda x: x[1])
                secenekler = ["1. En Yüksek Öncelik (Her Şeyden Önce)"]
                for i, (isim, oncelik) in enumerate(ek_odemeye_acik_borclar_info):
                    secenekler.append(f"Öncelik {i+2}. {isim}'den sonra")
                secenekler.append(f"Öncelik {len(ek_odemeye_acik_borclar_info) + 1}. En Sona Bırak")

                if ek_odemeye_acik_borclar_info:
                    oncelik_yeri_str = st.selectbox("Ek Ödeme Sırası", options=secenekler, index=0,
                                                    help="Bu borcun, mevcut borçlara göre ek ödeme sırası neresi olmalı?", key=f'priority_select_{context}')
                    debt_priority_str = oncelik_yeri_str
                else:
                    st.info("İlk ek ödemeye açık borcunuz bu olacak.")
                    debt_priority_str = "1. En Yüksek Öncelik (Her Şeyden Önce)"
            
        # --- COL F2: Tutar ve Süre Bilgileri (Koşullu Giriş) ---
        initial_faizli_tutar = 0.0
        debt_taksit = 0.0
        debt_kalan_ay = 0

        with col_f2:
            
            if is_harcama_sepeti:
                df_harcama = st.session_state.harcama_kalemleri_df
                kalem_isimleri = df_harcama['Kalem Adı'].tolist()
                
                secilen_kalemler = st.multiselect(
                    "Sepete Eklenecek Harcama Kalemleri",
                    options=kalem_isimleri,
                    default=kalem_isimleri,
                    key=f'harcama_multiselect_{context}'
                )
                
                if secilen_kalemler:
                    toplam_tutar = df_harcama[df_harcama['Kalem Adı'].isin(secilen_kalemler)]['Aylık Bütçe (TL)'].sum()
                else:
                    toplam_tutar = 0.0

                st.markdown(f"**Toplam Aylık Zorunlu Harcama (Bütçe):**")
                debt_taksit = st.number_input("", min_value=0.0, value=float(toplam_tutar), key=f'sabit_taksit_sepet_{context}', disabled=True, format="%.0f")
                harcama_kalemleri_isim = ", ".join(secilen_kalemler)
                
            elif is_kk:
                # Kredi Kartı Özel Alanlar (BDDK Kısıtları Uygulanır)
                max_taksit_ay_kk = st.session_state.tr_params['kk_taksit_max_ay']
                
                st.info("Kredi Kartı borcunun detaylarını girin.")
                kk_limit = st.number_input("Kart Limiti", min_value=1.0, value=150000.0, key=f'kk_limit_{context}')
                kk_kalan_ekstre = st.number_input("Kalan Ekstre Borcu (Faizli Kısım)", min_value=0.0, value=30000.0, key=f'kk_ekstre_{context}')
                kk_donem_ici = st.number_input("Dönem İçi İşlemler", min_value=0.0, value=5000.0, key=f'kk_donem_ici_{context}')
                debt_taksit = st.number_input("Gelecek Dönem Taksitleri (Aylık Ödeme)", min_value=0.0, value=7000.0, key=f'kk_taksit_aylik_{context}')
                
                debt_kalan_ay = st.number_input("Taksitlerin Ortalama Kalan Ayı",
                                                min_value=0,
                                                max_value=max_taksit_ay_kk,
                                                value=min(12, max_taksit_ay_kk),
                                                key=f'kk_taksit_kalan_ay_{context}')
                initial_faizli_tutar = kk_kalan_ekstre + kk_donem_ici
                
            elif is_kmh:
                # KMH Özel Alanlar
                kmh_limit = st.number_input("Ek Hesap Limiti", min_value=1.0, value=50000.0, key=f'kmh_limit_{context}')
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=0.0, value=15000.0, key=f'initial_tutar_{context}') # Kalan Anapara Tutarı
                st.markdown("---")
                st.markdown("Aşağıdaki alanlar Ek Hesap için alakasızdır.")
                
            else:
                # Diğer Kredi ve Sabit Giderler
                
                is_faiz_ana_disabled = is_sabit_gider or not (is_faizli_borc or is_sabit_kredi)
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", # Kalan Anapara Tutarı
                                                       min_value=0.0,
                                                       value=50000.0 if not is_faiz_ana_disabled else 0.0,
                                                       key=f'initial_tutar_{context}',
                                                       disabled=is_faiz_ana_disabled)
                
                is_taksit_disabled = not (is_sabit_gider or is_sabit_kredi)
                default_taksit = 5000.0 if not is_taksit_disabled else 0.0
                debt_taksit = st.number_input("Aylık Zorunlu Taksit/Gider Tutarı",
                                              min_value=0.0,
                                              value=default_taksit,
                                              key=f'sabit_taksit_{context}',
                                              disabled=is_taksit_disabled)
                
                # Kredi Kalan Ay Kısıtı (BDDK Kısıtları Uygulanır)
                is_kalan_ay_disabled = not is_sabit_kredi
                max_taksit_ay_kredi = st.session_state.tr_params['kredi_taksit_max_ay']
                kalan_ay_default = min(12, max_taksit_ay_kredi) if is_sabit_kredi else 0
                
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı",
                                                min_value=0,
                                                max_value=max_taksit_ay_kredi,
                                                value=kalan_ay_default,
                                                key=f'kalan_taksit_ay_{context}',
                                                disabled=is_kalan_ay_disabled)

                
        # --- COL F3: Faiz ve Asgari Ödeme Bilgileri (Koşullu Giriş) ---
        with col_f3:
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0
            debt_zorunlu_anapara_yuzdesi = 0.0
            
            is_faiz_disabled = is_sabit_kredi or is_sabit_gider or is_harcama_sepeti or not is_faizli_borc
            
            # Yasal Faiz Varsayılanları
            faiz_default_kk = st.session_state.tr_params['kk_aylik_akdi_faiz']
            faiz_default_kmh = st.session_state.tr_params['kmh_aylik_faiz']
            faiz_default = faiz_default_kk if is_kk else (faiz_default_kmh if is_kmh else 5.0)
            
            # Aylık Faiz Oranı
            debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)",
                                              value=faiz_default,
                                              step=0.05, min_value=0.0,
                                              key=f'debt_faiz_aylik_{context}',
                                              disabled=is_faiz_disabled) / 100.0
                
            # Kredi Kartı Asgari Ödeme Yüzdesi
            is_kk_asgari_disabled = not is_kk
            asgari_default_kk = st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default']
            
            debt_kk_asgari_yuzdesi = st.number_input("KK Asgari Ödeme Anapara Yüzdesi (%)",
                                                     value=asgari_default_kk,
                                                     step=1.0, min_value=0.0,
                                                     key=f'kk_asgari_{context}',
                                                     disabled=is_kk_asgari_disabled) / 100.0
            
            # Ek Hesap Zorunlu Anapara
            is_kmh_anapara_disabled = not is_kmh
            kmh_anapara_default = 5.0 if not is_kmh_anapara_disabled else 0.0
            debt_zorunlu_anapara_yuzdesi = st.number_input("KMH Zorunlu Anapara Kapama Yüzdesi (%)",
                                                           value=kmh_anapara_default,
                                                           step=1.0, min_value=0.0,
                                                           key=f'kmh_anapara_{context}',
                                                           disabled=is_kmh_anapara_disabled) / 100.0
            
            st.markdown("---")
            # Borç bittikten sonra giderin devam etme yüzdesi
            is_devam_disabled = not (is_sabit_gider or is_harcama_sepeti)
            devam_etme_yuzdesi_input = st.number_input(
                "Borç/Gider Bitiminden Sonra Devam Yüzdesi (%)",
                value=100.0 if is_harcama_sepeti else 0.0,
                min_value=0.0, max_value=100.0, step=1.0,
                key=f'devam_yuzdesi_{context}',
                disabled=is_devam_disabled,
                help="Sabit giderler için: Borç/Gider süresi bittiğinde, bu giderin yüzde kaçı simülasyonun geri kalanında 'Harcama Gideri' olarak düşülmeye devam etsin?"
            ) / 100.0
                
        submit_button = st.form_submit_button(label="Borç/Gider Ekle") # Yükümlülüğü Ekle -> Borç/Gider Ekle
        
        if submit_button:
            if is_harcama_sepeti and not harcama_kalemleri_isim:
                 st.error("Harcama Sepeti için en az bir kalem seçmelisiniz.")
                 return
                 
            final_debt_name = f"{debt_name} ({harcama_kalemleri_isim})" if is_harcama_sepeti else debt_name
            
            if is_kk:
                  add_debt(final_debt_name, initial_faizli_tutar, debt_priority_str, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi, debt_zorunlu_anapara_yuzdesi, kk_limit, 0.0)
                  
            elif is_kmh:
                  add_debt(final_debt_name, initial_faizli_tutar, debt_priority_str, debt_type, 0.0, 0, debt_faiz_aylik, 0.0, debt_zorunlu_anapara_yuzdesi, kmh_limit, 0.0)
            
            elif is_harcama_sepeti:
                  # HATA DÜZELTME 1: Kalan ay 0 olunca gider hiç uygulanmıyordu. Süresiz olması için 99999 yapıldı.
                  add_debt(final_debt_name, 0.0, '', "Sabit Gider (Harcama Sepeti)", debt_taksit, 99999, 0.0, 0.0, 0.0, 0.0, devam_etme_yuzdesi_input)
                  
            elif is_sabit_gider:
                  add_debt(final_debt_name, 0.0, '', debt_type, debt_taksit, 0, 0.0, 0.0, 0.0, 0.0, devam_etme_yuzdesi_input)
            
            else:
                  add_debt(final_debt_name, initial_faizli_tutar, debt_priority_str, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi, debt_zorunlu_anapara_yuzdesi, 0.0, 0.0)


# --- 5. Borç ve Gelir Yönetim Tabloları ---

def display_and_manage_debts():
    if st.session_state.borclar:
        st.subheader("📊 Mevcut Borçlar ve Giderler") # Yükümlülükler -> Borçlar ve Giderler
        
        display_df = pd.DataFrame(st.session_state.borclar)
        
        display_df = display_df[['isim', 'min_kural', 'tutar', 'sabit_taksit', 'faiz_aylik', 'oncelik']]
        
        display_df.columns = ["Yükümlülük Adı", "Kural", "Kalan Anapara", "Aylık Taksit/Gider", "Aylık Faiz (%)", "Öncelik"]
        
        display_df['Kalan Anapara'] = display_df['Kalan Anapara'].apply(format_tl)
        display_df['Aylık Taksit/Gider'] = display_df['Aylık Taksit/Gider'].apply(format_tl)
        display_df['Aylık Faiz (%)'] = (display_df['Aylık Faiz (%)'] * 100).apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(
            display_df,
            column_config={"index": "Index No (Silmek için Seçin)"},
            hide_index=False,
            key="current_debts_editor"
        )

        st.info("Kaldırmak istediğiniz borçların solundaki **index numarasını** seçerek 'Sil' butonuna basın.")
        
        debt_indices_to_delete = st.multiselect(
            "Silinecek Borcun Index Numarası",
            options=display_df.index.tolist(),
            key='debt_delete_select'
        )
        
        if st.button("Seçili Borç/Gideri Sil", type="secondary"): # Yükümlülüğü Sil -> Seçili Borç/Gideri Sil
            if not debt_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz borçların index numarasını seçin.")
                return
            
            st.session_state.borclar = [
                borc for i, borc in enumerate(st.session_state.borclar)
                if i not in debt_indices_to_delete
            ]
            st.success(f"{len(debt_indices_to_delete)} adet borç/gider listeden kaldırıldı.")
            st.rerun()
            
    else:
        st.info("Henüz eklenmiş bir borç veya gider bulunmamaktadır.")

def display_and_manage_incomes():
    if st.session_state.gelirler:
        st.subheader("💰 Mevcut Gelir Kaynakları")
        gelir_df = pd.DataFrame(st.session_state.gelirler)
        gelir_df = gelir_df[['isim', 'tutar', 'baslangic_ay', 'artis_yuzdesi', 'tek_seferlik']]
        gelir_df.columns = ["Gelir Adı", "Aylık Tutar", "Başlangıç Ayı", "Artış Yüzdesi", "Tek Seferlik Mi?"]
        gelir_df['Aylık Tutar'] = gelir_df['Aylık Tutar'].apply(format_tl)
        gelir_df['Artış Yüzdesi'] = (gelir_df['Artış Yüzdesi'] * 100).apply(lambda x: f"{x:.2f}%")
        st.dataframe(gelir_df, hide_index=False)
    else:
        st.info("Henüz eklenmiş bir gelir kaynağı bulunmamaktadır.")

# --- 6. Simülasyon Motoru ---

def simule_borc_planı(borclar_initial, gelirler_initial, **sim_params):
    
    if not borclar_initial or not gelirler_initial:
        return None

    # HATA DÜZELTME 2: Her simülasyon başlangıcında tek seferlik gelirlerin durumunu sıfırla.
    st.session_state.tek_seferlik_gelir_isaretleyicisi.clear()

    # Derin kopya
    mevcut_borclar = copy.deepcopy(borclar_initial)
    mevcut_gelirler = copy.deepcopy(gelirler_initial)
    
    # Başlangıç değişkenleri
    ay_sayisi = 0
    mevcut_birikim = sim_params.get('baslangic_birikim', 0.0)
    birikime_ayrilan = sim_params.get('aylik_zorunlu_birikim', 0.0)
    faiz_carpani = sim_params.get('faiz_carpani', 1.0)
    agresiflik_carpan = sim_params.get('agresiflik_carpan', 1.0)
    birikim_artis_aylik = sim_params.get('birikim_artis_aylik', 0.0) / 12 / 100
    
    toplam_faiz_maliyeti = 0.0
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    
    aylik_sonuclar = []
    
    # İlk ay değerlerini tutmak için
    ilk_ay_toplam_gelir = 0
    ilk_ay_toplam_gider = 0

    # ----------------------------------------------------
    # Simülasyon Ana Döngüsü
    # ----------------------------------------------------
    while any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']) or ay_sayisi < 1:
        ay_sayisi += 1
