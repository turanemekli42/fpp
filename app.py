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

# --- 1. Sabitler ve Kurallar ---
STRATEJILER = {
    "Pasif (Minimum Ek Ödeme)": 0.0,
    "Temkinli (Yüzde 50)": 0.5,
    "Saldırgan (Maksimum Ek Ödeme)": 1.0,
    "Ultra Agresif (x1.5 Maksimum)": 1.5,
}

ONCELIK_STRATEJILERI = {
    "Borç Çığı (Avalanche - Önce Faiz)": "Avalanche",
    "Borç Kartopu (Snowball - Önce Tutar)": "Snowball",
    "Kullanıcı Tanımlı Sıra": "Kullanici"
}

# Para formatlama fonksiyonu
def format_tl(tutar):
    return f"{int(tutar):,} TL" if tutar is not None else "0 TL"

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
        'kk_taksit_max_ay': 12, # KK Mal/Hizmet max taksit sayısı
        'kk_asgari_odeme_yuzdesi_default': 20.0, # %25.000 TL altı için %20 (Basitlik için varsayılan)
        'kk_aylik_akdi_faiz': 3.66, # % Yasal akdi faiz (Örnek değer)
        'kk_aylik_gecikme_faiz': 3.96, # % Yasal gecikme faizi (Örnek değer)
        'kmh_aylik_faiz': 5.0, # KMH/Kredilere uygulanabilecek güncel maksimum faiz oranları (piyasa oranları esas alınmıştır)
        'kredi_taksit_max_ay': 36, # İhtiyaç kredisi için BDDK max ay
    }


# --- 3. Yardımcı Fonksiyonlar ---

def hesapla_min_odeme(borc, faiz_carpani=1.0):
    kural = borc.get('min_kural')
    tutar = borc.get('tutar', 0)
    
    if kural in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
        # Sabit Giderler ve KK Taksitler (Gider olarak düşer)
        return borc.get('sabit_taksit', 0)
    
    elif kural == 'SABIT_TAKSIT_ANAPARA':
        # Kredi Taksiti (Anaparası düşer, faiz ayrıca hesaplanır)
        # Basitlik için sadece sabit taksiti zorunlu ödeme kabul ediyoruz.
        return borc.get('sabit_taksit', 0)
    
    elif kural == 'ASGARI_FAIZ': # Kredi Kartı
        # Asgari ödeme: Kalan borcun yüzdesi
        # Tutar zaten faiz eklenmiş hali olabilir, ancak asgari ödeme genellikle anapara + önceki faiz üzerinden hesaplanır.
        # Basit Simülasyon: Kalan borcun yüzdesi (BDDK kuralı)
        asgari_anapara_yuzdesi = borc.get('kk_asgari_yuzdesi', 0)
        # Ödeme = Tutarın %X'i. 
        # NOT: Gerçek asgari ödeme karmaşıktır. Burada basitleştirilmiş hali kullanıldı.
        return tutar * asgari_anapara_yuzdesi
    
    elif kural in ['FAIZ_ART_ANAPARA', 'FAIZ']: # KMH ve Diğer Faizli
        # Yasal olarak borçlu olunan tutarın bir yüzdesi veya tamamı (KMH'da genelde %5 vb.)
        zorunlu_anapara_yuzdesi = borc.get('zorunlu_anapara_yuzdesi', 0)
        return tutar * zorunlu_anapara_yuzdesi
    
    return 0


def add_debt(isim, faizli_anapara, oncelik_str, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi, kk_limit=0.0, devam_etme_yuzdesi=0.0):
    
    borc_listesi = []
    final_priority = 1 

    if oncelik_str:
        # Borç listesi dolu ise, en yüksek önceliği 1 kabul edip +1000 ekleyerek sabit giderlerden ayırıyoruz.
        priority_val = int(oncelik_str.split('.')[0])
        final_priority = priority_val + 1000 

    # 2. Borç Objektlerini Oluşturma
    
    if borc_tipi == "Sabit Gider (Harcama Sepeti)" or borc_tipi in ["Sabit Kira Gideri", "Ev Kredisi Taksiti"]:
        # Sabit Giderler (KMH/KK limitleri 0)
        kural_type = "SABIT_GIDER"
        
        borc_listesi.append({
            "isim": isim,
            "tutar": 0, "min_kural": kural_type,
            "oncelik": 1, "sabit_taksit": sabit_taksit,
            "kalan_ay": kalan_ay if borc_tipi != "Sabit Kira Gideri" else 99999, 
            "faiz_aylik": 0, "kk_asgari_yuzdesi": 0,
            "limit": 0, "devam_etme_yuzdesi": devam_etme_yuzdesi
        })
    
    # Kredi Kartı
    elif borc_tipi == "Kredi Kartı":
        # 1. KK Taksitli Alışverişler (Gider olarak, borç saldırısına kapalı)
        if sabit_taksit > 0 and kalan_ay > 0:
            borc_listesi.append({
                "isim": f"{isim} (Taksitler)",
                "tutar": sabit_taksit * kalan_ay, "min_kural": "SABIT_TAKSIT_GIDER",
                "oncelik": 1, "sabit_taksit": sabit_taksit,
                "kalan_ay": kalan_ay, "faiz_aylik": 0, "kk_asgari_yuzdesi": 0,
                "limit": kk_limit, "devam_etme_yuzdesi": 0.0
            })
        
        # 2. KK Dönem Borcu (Faizli, borç saldırısına açık)
        if faizli_anapara > 0:
             borc_listesi.append({
                "isim": f"{isim} (Dönem Borcu)",
                "tutar": faizli_anapara, "min_kural": "ASGARI_FAIZ", 
                "oncelik": final_priority, 
                "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
                "kalan_ay": 99999,
                "limit": kk_limit, "devam_etme_yuzdesi": 0.0
            })
    
    # Ek Hesap (KMH)
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

    # Kredi (Sabit Taksit)
    elif borc_tipi == "Kredi (Sabit Taksit)":
        borc_listesi.append({
            "isim": isim,
            "tutar": faizli_anapara, "min_kural": "SABIT_TAKSIT_ANAPARA",
            "oncelik": final_priority,
            "sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay,
            "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0,
            "limit": 0, "devam_etme_yuzdesi": 0.0
        })
        
    # Diğer Faizli Borç
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
        st.success(f"'{isim}' yükümlülüğü başarıyla eklendi.")


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
    st.subheader(f"Yükümlülükleri/Borçları Yönet ({context})")
    
    kk_limit = 0.0 
    kmh_limit = 0.0
    harcama_kalemleri_isim = ""

    with st.form(f"new_debt_form_{context}", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns(3) 
        
        # --- COL F1: Temel Bilgiler ---
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Borç", key=f'debt_name_{context}')
            
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
            
            # YENİ ÖNCELİK MANTIK BLOĞU (Sadece ek ödemeye açık borçlar için)
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
                secenekler.append(f"Öncelik {len(ek_odemeye_acik_borclar_info) + 2}. En Sona Bırak")

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
                # HARCAMA SEPETİ ÖZEL ALANLAR
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
                kk_kalan_ekstre = st.number_input("Kalan Ekstre Borcu (Faizli Anapara)", min_value=0.0, value=30000.0, key=f'kk_ekstre_{context}')
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
                initial_faizli_tutar = st.number_input("Kalan Ek Hesap Borç Anaparası", min_value=0.0, value=15000.0, key=f'initial_tutar_{context}')
                st.markdown("---")
                st.markdown("Aşağıdaki alanlar Ek Hesap için alakasızdır.")
                
            else:
                # Diğer Kredi ve Sabit Giderler
                
                is_faiz_ana_disabled = is_sabit_gider or not (is_faizli_borc or is_sabit_kredi)
                initial_faizli_tutar = st.number_input("Faizli Kalan Borç Anaparası", 
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
            # YENİ ALAN: Borç bittikten sonra giderin devam etme yüzdesi
            is_devam_disabled = not (is_sabit_gider or is_harcama_sepeti)
            devam_etme_yuzdesi_input = st.number_input(
                "Borç/Gider Bitiminden Sonra Devam Yüzdesi (%)",
                value=100.0 if is_harcama_sepeti else 0.0, 
                min_value=0.0, max_value=100.0, step=1.0, 
                key=f'devam_yuzdesi_{context}', 
                disabled=is_devam_disabled,
                help="Sabit giderler için: Borç/Gider süresi bittiğinde, bu giderin yüzde kaçı simülasyonun geri kalanında 'Harcama Gideri' olarak düşülmeye devam etsin?"
            ) / 100.0
                
        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        
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
                 add_debt(final_debt_name, 0.0, '', "Sabit Gider (Harcama Sepeti)", debt_taksit, 0, 0.0, 0.0, 0.0, 0.0, devam_etme_yuzdesi_input)
                 
            elif is_sabit_gider:
                 add_debt(final_debt_name, 0.0, '', debt_type, debt_taksit, 0, 0.0, 0.0, 0.0, 0.0, devam_etme_yuzdesi_input)
            
            else:
                 add_debt(final_debt_name, initial_faizli_tutar, debt_priority_str, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi, debt_zorunlu_anapara_yuzdesi, 0.0, 0.0)


# --- 5. Borç ve Gelir Yönetim Tabloları ---

def display_and_manage_debts():
    if st.session_state.borclar:
        st.subheader("📊 Mevcut Yükümlülükler")
        
        display_df = pd.DataFrame(st.session_state.borclar)
        
        display_df = display_df[['isim', 'min_kural', 'tutar', 'sabit_taksit', 'faiz_aylik', 'oncelik']]
        
        display_df.columns = ["Yükümlülük Adı", "Kural", "Kalan Anapara", "Aylık Taksit/Gider", "Aylık Faiz (%)", "Öncelik"]
        
        display_df['Kalan Anapara'] = display_df['Kalan Anapara'].apply(lambda x: f"{int(x):,} TL")
        display_df['Aylık Taksit/Gider'] = display_df['Aylık Taksit/Gider'].apply(lambda x: f"{int(x):,} TL")
        display_df['Aylık Faiz (%)'] = (display_df['Aylık Faiz (%)'] * 100).apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(
            display_df,
            column_config={"index": "Index No (Silmek için Seçin)"},
            hide_index=False,
            key="current_debts_editor"
        )

        st.info("Kaldırmak istediğiniz borçların solundaki **index numarasını** seçerek 'Yükümlülüğü Sil' butonuna basın.")
        
        debt_indices_to_delete = st.multiselect(
            "Silinecek Borcun Index Numarası", 
            options=display_df.index.tolist(),
            key='debt_delete_select'
        )
        
        if st.button("Yükümlülüğü Sil", type="secondary"):
            if not debt_indices_to_delete:
                st.warning("Lütfen silmek istediğiniz borçların index numarasını seçin.")
                return
            
            st.session_state.borclar = [
                borc for i, borc in enumerate(st.session_state.borclar) 
                if i not in debt_indices_to_delete
            ]
            st.success(f"{len(debt_indices_to_delete)} adet yükümlülük listeden kaldırıldı.")
            st.rerun()
            
    else:
        st.info("Henüz eklenmiş bir yükümlülük bulunmamaktadır.")

def display_and_manage_incomes():
    if st.session_state.gelirler:
        st.subheader("💰 Mevcut Gelir Kaynakları")
        gelir_df = pd.DataFrame(st.session_state.gelirler)
        gelir_df = gelir_df[['isim', 'tutar', 'baslangic_ay', 'artis_yuzdesi', 'tek_seferlik']]
        gelir_df.columns = ["Gelir Adı", "Aylık Tutar", "Başlangıç Ayı", "Artış Yüzdesi", "Tek Seferlik Mi?"]
        gelir_df['Aylık Tutar'] = gelir_df['Aylık Tutar'].apply(lambda x: f"{int(x):,} TL")
        gelir_df['Artış Yüzdesi'] = (gelir_df['Artış Yüzdesi'] * 100).apply(lambda x: f"{x:.2f}%")
        st.dataframe(gelir_df, hide_index=False)
    else:
        st.info("Henüz eklenmiş bir gelir kaynağı bulunmamaktadır.")

# --- 6. Simülasyon Motoru ---

def simule_borc_planı(borclar_initial, gelirler_initial, **sim_params):
    
    if not borclar_initial or not gelirler_initial:
        return None

    # Derin kopya: Simülasyon sırasında ana listeyi değiştirmemek için
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
    
    # ----------------------------------------------------
    # Simülasyon Ana Döngüsü
    # ----------------------------------------------------
    while any(b['tutar'] > 1 for b in mevcut_borclar) or ay_sayisi < 1:
        ay_sayisi += 1
        ay_adi = f"Ay {ay_sayisi}"
        
        # 1. Gelir Hesaplama
        toplam_gelir = 0.0
        for gelir in mevcut_gelirler:
            if ay_sayisi >= gelir['baslangic_ay']:
                # Yıllık artış hesaplama
                artis_carpan = (1 + gelir['artis_yuzdesi']) ** ((ay_sayisi - gelir['baslangic_ay']) / 12)
                toplam_gelir += gelir['tutar'] * artis_carpan
                
                # Tek seferlik gelir kontrolü (Simülasyon motorunun basitliğini korumak için, gelir listesinden kaldırılır)
                if gelir['tek_seferlik'] and ay_sayisi == gelir['baslangic_ay']:
                     if gelir['isim'] not in st.session_state.tek_seferlik_gelir_isaretleyicisi:
                         st.session_state.tek_seferlik_gelir_isaretleyicisi.add(gelir['isim'])
                         # NOT: Tek seferlik gelirler bir sonraki ayda gelir listesinden kaldırılmalıdır.
                         # Basitlik için burada bırakıldı, ancak kullanıcı Gelir Silme fonksiyonunu kullanmalı.


        # 2. Minimum Borç Ödemeleri ve Sabit Giderler
        zorunlu_gider_toplam = birikime_ayrilan # Aylık sabit birikim zorunlu gider sayılır
        min_borc_odeme_toplam = 0.0
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 1 or borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                
                min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                
                if borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                    # Sabit Giderler
                    zorunlu_gider_toplam += borc.get('sabit_taksit', 0)
                else:
                    # Minimum Borç Ödemeleri (Faizli ve Taksitli Krediler)
                    min_borc_odeme_toplam += min_odeme

        # İlk ay için gelir ve gider toplamlarını kaydet
        if ay_sayisi == 1:
            ilk_ay_toplam_gelir = toplam_gelir
            ilk_ay_toplam_gider = zorunlu_gider_toplam + min_borc_odeme_toplam


        # 3. Borç Saldırı Gücü (Ek Ödeme Gücü) Hesaplama
        kalan_nakit = toplam_gelir - zorunlu_gider_toplam - min_borc_odeme_toplam
        saldırı_gucu = max(0, kalan_nakit * agresiflik_carpan)


        # 4. Borçlara Ödeme Uygulama
        
        # a) Faiz ve Minimum Ödeme İşlemleri
        for borc in mevcut_borclar:
            is_faizli_borc = borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']

            if borc['tutar'] > 0 and is_faizli_borc:
                
                # BDDK Kuralı: KK'da min ödeme yapılmazsa Gecikme Faizi uygulanır (Basitlik için uygulanmadı)
                
                etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani 
                toplam_faiz_maliyeti += eklenen_faiz
                
                min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                
                # Borca faiz eklenir, min ödeme düşülür
                borc['tutar'] += eklenen_faiz 
                borc['tutar'] -= min_odeme
                
                # Kredi Taksit Sayısı Düşürme
                if borc['min_kural'] == 'SABIT_TAKSIT_ANAPARA' and borc['kalan_ay'] > 0:
                     borc['kalan_ay'] -= 1
        
        
        # b) Saldırı Gücünü Uygulama (Önceliğe Göre Sıralama)
        saldırı_kalan = saldırı_gucu

        # **MANUEL ÖNCELİK ENTEGRASYONU**
        manuel_oncelik_kullan = (
            sim_params['oncelik_stratejisi'] == 'Kullanici' and 
            st.session_state.get('manuel_oncelik_listesi')
        )
        
        if manuel_oncelik_kullan:
            manuel_oncelik_dict = st.session_state.manuel_oncelik_listesi
            
            for borc in mevcut_borclar:
                if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                    yeni_oncelik = manuel_oncelik_dict.get(borc['isim'])
                    if yeni_oncelik is not None:
                        borc['oncelik'] = yeni_oncelik # Güncel manuel önceliği atama

            mevcut_borclar.sort(key=lambda x: x['oncelik'])
            
        else:
            # Avalanche, Snowball veya Varsayılan mantık uygulanır
            if sim_params['oncelik_stratejisi'] == 'Avalanche':
                mevcut_borclar.sort(key=lambda x: (x['faiz_aylik'], x['tutar']), reverse=True)
            elif sim_params['oncelik_stratejisi'] == 'Snowball':
                mevcut_borclar.sort(key=lambda x: x['tutar'])
            else:
                mevcut_borclar.sort(key=lambda x: x['oncelik'])


        # Saldırıyı Uygula
        kapanan_borclar_listesi = []
        for borc in mevcut_borclar:
            is_ek_odemeye_acik = borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
            
            if borc['tutar'] > 1 and saldırı_kalan > 0 and is_ek_odemeye_acik:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0
        
        
        # c) Kalan Saldırı Gücünü Birikime Aktarma
        mevcut_birikim += saldırı_kalan
        
        # Birikim Faizini Ekleme (Aylık bazda)
        mevcut_birikim *= (1 + birikim_artis_aylik)


        # d) Kredi Kartı/KMH Limit Kontrolü (Gerekli ama basitlik için tam limit aşımı kontrolü atlandı)
        # NOT: Gerçek uygulamada buraya limit aşımı kontrolü eklenmelidir.
        
        
        # 5. Sonuçları Kaydetme
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir),
            'Toplam Zorunlu Giderler': round(zorunlu_gider_toplam),
            'Min. Borç Ödemeleri': round(min_borc_odeme_toplam),
            'Borç Saldırı Gücü': round(saldırı_gucu),
            'Aylık Birikim Katkısı': round(birikime_ayrilan + saldırı_kalan),
            'Kapanan Borçlar': ", ".join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])),
            'Toplam Birikim': round(mevcut_birikim)
        })

        if ay_sayisi > 360: # 30 yıl sonra simülasyonu durdur
            st.warning("‼️ Simülasyon 30 yılı aştığı için durduruldu. Borçlar tamamen kapanmamış olabilir.")
            break
            
    # Döngü sonrası temizlik ve özet
    if ay_sayisi == 1: # Borç hiç yoksa
        return {
            "df": pd.DataFrame(aylik_sonuclar), "ay_sayisi": 0, "toplam_faiz": 0,
            "toplam_birikim": mevcut_birikim, "baslangic_faizli_borc": 0,
            "ilk_ay_gelir": toplam_gelir, "ilk_ay_gider": zorunlu_gider_toplam
        }

    return {
        "df": pd.DataFrame(aylik_sonuclar),
        "ay_sayisi": ay_sayisi,
        "toplam_faiz": round(toplam_faiz_maliyeti),
        "toplam_birikim": round(mevcut_birikim),
        "baslangic_faizli_borc": round(baslangic_faizli_borc),
        "ilk_ay_gelir": ilk_ay_toplam_gelir,
        "ilk_ay_gider": ilk_ay_toplam_gider,
        "limit_asimi": False
    }


# --- 7. Ana Uygulama Düzeni ---

st.title("Borç Kapatma ve Finansal Planlama Simülasyonu")

tab_advanced, tab_basic, tab_rules = st.tabs(["🚀 Gelişmiş Planlama", "✨ Basit Planlama", "⚙️ Yönetici Kuralları"])

# --- TAB 1: Gelişmiş Planlama ---
with tab_advanced:
    st.header("🚀 Gelişmiş Planlama ve Senaryo Yönetimi")
    st.info("Borç öncelikleri, faiz çarpanları ve birikim hedeflerini detaylıca yönetin.")
    
    col_st1, col_st2, col_st3 = st.columns(3)
    with col_st1:
        AGRESIFLIK_ADVANCED = st.selectbox("Ek Ödeme Agresifliği", options=list(STRATEJILER.keys()), index=2, key='agresiflik_adv')
        ONCELIK_ADVANCED = st.selectbox("Borç Kapatma Yöntemi", options=list(ONCELIK_STRATEJILERI.keys()), index=0, key='oncelik_adv')
    
    with col_st2:
        FAIZ_CARPANI_ADVANCED = st.slider("Faiz Oranı Çarpanı", min_value=0.5, max_value=2.0, value=1.0, step=0.1, key='faiz_carpan_adv')
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
            odemeye_acik_borclar = [
                b for b in st.session_state.borclar 
                if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
            ]
            if odemeye_acik_borclar:
                siralama_df = pd.DataFrame([
                    {'isim': b['isim'], 'mevcut_oncelik': b['oncelik'] - 1000, 'yeni_oncelik': b['oncelik'] - 1000} 
                    for b in odemeye_acik_borclar
                ])
                siralama_df = siralama_df.sort_values(by='yeni_oncelik', ascending=True)

                st.info("Borç önceliklerini manuel olarak ayarlamak için **'Yeni Öncelik'** sütunundaki numaraları değiştirin.")

                edited_siralama_df = st.data_editor(
                    siralama_df,
                    column_config={
                        "yeni_oncelik": st.column_config.NumberColumn("Yeni Öncelik", min_value=1, step=1),
                        "isim": st.column_config.TextColumn("Borç Adı", disabled=True),
                        "mevcut_oncelik": st.column_config.TextColumn("Mevcut Sıra", disabled=True)
                    },
                    hide_index=True,
                    key='advanced_priority_editor'
                )
                # Manuel öncelik değeri +1000 olarak kaydedilir, çünkü sabit giderlerden ayrılması gerekir.
                st.session_state.manuel_oncelik_listesi = edited_siralama_df.set_index('isim')['yeni_oncelik'].apply(lambda x: x + 1000).to_dict()
            else:
                st.info("Ek ödemeye açık borç (KK, KMH, Kredi) bulunmamaktadır.")
        else:
            st.warning("Lütfen önce borç yükümlülüklerini ekleyin.")
    else:
        st.info("Manuel sıralama, sadece **'Borç Kapatma Yöntemi'** **Kullanıcı Tanımlı Sıra** olarak seçildiğinde geçerlidir.")

    st.markdown("---")
    display_and_manage_incomes()
    display_and_manage_debts()
    
    st.markdown("---")
    is_disabled_advanced = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_advanced = st.button("GELİŞMİŞ PLAN OLUŞTUR", type="primary", disabled=is_disabled_advanced, key="calc_adv")


# --- TAB 2: Basit Planlama ---
with tab_basic:
    st.header("✨ Hızlı ve Varsayılan Planlama")
    
    varsayilan_agresiflik_str = st.session_state.get('default_agressiflik', 'Saldırgan (Maksimum Ek Ödeme)')
    varsayilan_oncelik_str = st.session_state.get('default_oncelik', 'Borç Çığı (Avalanche - Önce Faiz)')
    varsayilan_artis = st.session_state.get('default_aylik_artis', 3.5)
    
    col_st1, col_st2 = st.columns(2)
    with col_st1:
         BIRIKIM_TIPI_BASIC = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_basic')
         AYLIK_ZORUNLU_BIRIKIM_BASIC = st.number_input("Aylık Zorunlu Birikim Tutarı", value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik_basic', disabled=BIRIKIM_TIPI_BASIC != "Aylık Sabit Tutar")
         TOPLAM_BIRIKIM_HEDEFI_BASIC = st.number_input("Hedef Toplam Birikim Tutarı", value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam_basic', disabled=BIRIKIM_TIPI_BASIC != "Borç Bitimine Kadar Toplam Tutar")
         BASLANGIC_BIRIKIM_BASIC = st.number_input("Mevcut Başlangıç Birikimi", value=0, step=1000, min_value=0, key='baslangic_birikim_basic')
    with col_st2:
        st.markdown(f"**Borç Kapatma Yöntemi:** **{varsayilan_oncelik_str}**")
        st.markdown(f"**Ek Ödeme Agresifliği:** **{varsayilan_agresiflik_str}**")
        st.markdown(f"**Birikim Değerlemesi:** TL Mevduat (Yıllık **%{varsayilan_artis}** Artış)")

    st.markdown("---")
    render_income_form("basic")
    st.markdown("---")
    render_debt_form("basic")

    st.markdown("---")
    display_and_manage_incomes()
    display_and_manage_debts()
    
    st.markdown("---")
    is_disabled_basic = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_basic = st.button("BORÇ KAPATMA PLANINI OLUŞTUR", type="primary", disabled=is_disabled_basic, key="calc_basic")


# --- TAB 3: Yönetici Kuralları ---
with tab_rules:
    st.header("Simülasyon Kurallarını Yönet")
    
    st.subheader("Basit Planlama Varsayılanlarını Ayarla")
    
    col_r1, col_r2, col_r3 = st.columns(3)
    
    with col_r1:
        DEFAULT_AGRESSIFLIK = st.selectbox(
            "Varsayılan Ek Ödeme Agresifliği", 
            options=list(STRATEJILER.keys()),
            index=2, 
            key='default_agressiflik'
        )
    
    with col_r2:
        DEFAULT_ONCELIK = st.selectbox(
            "Varsayılan Borç Kapatma Yöntemi",
            options=list(ONCELIK_STRATEJILERI.keys()),
            index=0, 
            key='default_oncelik'
        )
        
    with col_r3:
        DEFAULT_ARTIS_YUZDESI = st.number_input(
            "Varsayılan Birikim Yıllık Artışı (%)",
            value=3.5, min_value=0.0, step=0.1,
            key='default_aylik_artis'
        )
        
    st.markdown("---")
    st.subheader("🇹🇷 BDDK ve Yasal Limitler (Türkiye)")
    st.warning("Bu değerler yasal zorunluluklardır ve simülasyonun gerçekçiliği için önemlidir. Gerekmedikçe değiştirmeyiniz.")
    
    col_l1, col_l2, col_l3 = st.columns(3)
    
    with col_l1:
        st.session_state.tr_params['kk_taksit_max_ay'] = st.number_input(
            "KK Mal/Hizmet Max Taksit Ayı",
            min_value=1, value=st.session_state.tr_params['kk_taksit_max_ay'], step=1,
            key='bddk_kk_taksit_max'
        )
        st.session_state.tr_params['kk_aylik_akdi_faiz'] = st.number_input(
            "KK Aylık Akdi Faiz (%)",
            min_value=0.0, value=st.session_state.tr_params['kk_aylik_akdi_faiz'], step=0.01,
            key='bddk_kk_faiz'
        )
        
    with col_l2:
        st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'] = st.number_input(
            "KK Asgari Ödeme Yüzdesi (%) (Örnek)",
            min_value=0.0, max_value=100.0, value=st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'], step=1.0,
            key='bddk_kk_asgari_yuzde'
        )
        st.session_state.tr_params['kk_aylik_gecikme_faiz'] = st.number_input(
            "KK Aylık Gecikme Faiz (%)",
            min_value=0.0, value=st.session_state.tr_params['kk_aylik_gecikme_faiz'], step=0.01,
            key='bddk_kk_gecikme'
        )
        
    with col_l3:
        st.session_state.tr_params['kredi_taksit_max_ay'] = st.number_input(
            "İhtiyaç Kredisi Max Taksit Ayı",
            min_value=1, value=st.session_state.tr_params['kredi_taksit_max_ay'], step=1,
            key='bddk_kredi_max'
        )
        st.session_state.tr_params['kmh_aylik_faiz'] = st.number_input(
            "KMH/Kredi Piyasa Faizi (%) (Max)",
            min_value=0.0, value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.1,
            key='bddk_kmh_faiz'
        )
        
    st.markdown("---")
    st.subheader("💳 Aylık Harcama Kalemleri Kütüphanesi")
    
    edited_df = st.data_editor(
        st.session_state.harcama_kalemleri_df,
        column_config={
            "Kalem Adı": st.column_config.TextColumn("Kalem Adı", required=True),
            "Aylık Bütçe (TL)": st.column_config.NumberColumn(
                "Aylık Bütçe (TL)",
                min_value=0,
                step=100,
                format="%.0f TL",
            ),
        },
        num_rows="dynamic",
        hide_index=True,
        key='harcama_editor'
    )
    
    st.session_state.harcama_kalemleri_df = edited_df

    toplam_butce = st.session_state.harcama_kalemleri_df['Aylık Bütçe (TL)'].sum()
    st.markdown(f"**Tanımlanan Toplam Aylık Bütçe:** **{int(toplam_butce):,} TL**")
    st.markdown("---")
    

# --- 8. Hesaplama Tetikleyicileri ---

if calculate_button_advanced or calculate_button_basic:
    
    if calculate_button_advanced:
        context = "advanced"
        sim_params = {
            'agresiflik_carpan': STRATEJILER[AGRESIFLIK_ADVANCED],
            'oncelik_stratejisi': ONCELIK_STRATEJILERI[ONCELIK_ADVANCED],
            'faiz_carpani': FAIZ_CARPANI_ADVANCED,
            'birikim_artis_aylik': AYLIK_ARTIS_ADVANCED,
            'aylik_zorunlu_birikim': AYLIK_ZORUNLU_BIRIKIM_ADVANCED if BIRIKIM_TIPI_ADVANCED == "Aylık Sabit Tutar" else 0,
            'baslangic_birikim': BASLANGIC_BIRIKIM_ADVANCED
        }
    else: # Basit Planlama
        context = "basic"
        sim_params = {
            'agresiflik_carpan': STRATEJILER[varsayilan_agresiflik_str],
            'oncelik_stratejisi': ONCELIK_STRATEJILERI[varsayilan_oncelik_str],
            'faiz_carpani': 1.0, # Basit planda faiz çarpanı 1.0
            'birikim_artis_aylik': st.session_state.get('default_aylik_artis', 3.5),
            'aylik_zorunlu_birikim': AYLIK_ZORUNLU_BIRIKIM_BASIC if BIRIKIM_TIPI_BASIC == "Aylık Sabit Tutar" else 0,
            'baslangic_birikim': BASLANGIC_BIRIKIM_BASIC
        }

    # Simülasyonu Çalıştır
    sonuc = simule_borc_planı(st.session_state.borclar, st.session_state.gelirler, **sim_params)

    if sonuc:
        with st.container():
            st.success("✅ Simülasyon başarıyla tamamlandı!")
            
            # Sonuç Özet Paneli
            kapanma_suresi_yil = sonuc['ay_sayisi'] // 12
            kapanma_suresi_ay = sonuc['ay_sayisi'] % 12
            
            st.header("📊 Finansal Hedef Özeti")
            col_res1, col_res2, col_res3, col_res4 = st.columns(4)
            
            col_res1.metric("Borç Kapanma Süresi", f"{kapanma_suresi_yil} Yıl {kapanma_suresi_ay} Ay", "")
            col_res2.metric("Toplam Borç Başlangıcı", format_tl(sonuc['baslangic_faizli_borc']), "")
            col_res3.metric("Ödenen Toplam Faiz Maliyeti", format_tl(sonuc['toplam_faiz']), "")
            col_res4.metric("Kapanış Anındaki Toplam Birikim", format_tl(sonuc['toplam_birikim']), "")
            
            st.markdown("---")
            st.header("📈 Aylık Detaylı Simülasyon Sonuçları")
            st.dataframe(sonuc['df'], hide_index=True)
