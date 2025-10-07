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
        try:
            priority_val = int(oncelik_str.split('.')[0])
            final_priority = priority_val + 1000
        except (ValueError, IndexError):
            final_priority = 9999 # Hata durumunda en sona at

    # Borç objelerini oluştur
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

    if borc_tipi == "Kredi Kartı":
        # Taksitler için ayrı bir 'sabit gider' objesi oluştur
        if sabit_taksit > 0 and kalan_ay > 0:
            taksit_obj = {
                "isim": f"{isim} (Taksitler)",
                "tutar": 0, # Taksitlerin anaparası zaten kk dönem borcuna dahil
                "min_kural": "SABIT_TAKSIT_GIDER",
                "oncelik": 1, # Taksitler her zaman önceliklidir
                "sabit_taksit": sabit_taksit,
                "kalan_ay": kalan_ay,
                "faiz_aylik": 0, "kk_asgari_yuzdesi": 0, "limit": 0, "devam_etme_yuzdesi": 0.0
            }
            borc_listesi.append(taksit_obj)
        # Faizli anapara için ana borç objesini ekle
        if faizli_anapara > 0:
            yeni_borc["isim"] = f"{isim} (Dönem Borcu)"
            yeni_borc["min_kural"] = "ASGARI_FAIZ"
            borc_listesi.append(yeni_borc)

    elif borc_tipi == "Ek Hesap (KMH)":
        yeni_borc["min_kural"] = "FAIZ_ART_ANAPARA"
        borc_listesi.append(yeni_borc)

    elif borc_tipi == "Kredi (Sabit Taksit)":
        yeni_borc["min_kural"] = "SABIT_TAKSIT_ANAPARA"
        borc_listesi.append(yeni_borc)

    elif borc_tipi == "Diğer Faizli Borç":
        yeni_borc["min_kural"] = "FAIZ"
        borc_listesi.append(yeni_borc)
        
    elif borc_tipi in ["Sabit Kira Gideri", "Ev Kredisi Taksiti", "Aylık Harcama Sepeti (Kütüphaneden)"]:
        yeni_borc["min_kural"] = "SABIT_GIDER"
        yeni_borc["oncelik"] = 1 # Giderler en önceliklidir
        yeni_borc["tutar"] = 0 # Giderlerin anaparası olmaz
        yeni_borc["faiz_aylik"] = 0
        yeni_borc["kalan_ay"] = 99999 if borc_tipi in ["Sabit Kira Gideri", "Aylık Harcama Sepeti (Kütüphaneden)"] else (kalan_ay if kalan_ay > 0 else 99999)
        borc_listesi.append(yeni_borc)

    if borc_listesi:
        st.session_state.borclar.extend(borc_listesi)
        st.success(f"'{isim}' borcu/gideri başarıyla eklendi.")
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

# YENİLENMİŞ FONKSİYON
def render_debt_form(context):
    st.subheader(f"Borçları ve Giderleri Yönet ({context})")
    
    # Tüm olası değişkenleri form başında None veya 0 olarak başlatalım
    kk_limit = 0.0
    kmh_limit = 0.0
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
            debt_name = st.text_input("Borç/Gider Adı", value="Yeni Borç", key=f'debt_name_{context}')
            
            debt_type = st.selectbox("Yükümlülük Tipi",
                                     ["Kredi Kartı", "Ek Hesap (KMH)", "Kredi (Sabit Taksit)", "Diğer Faizli Borç",
                                      "--- Sabit Giderler ---",
                                      "Sabit Kira Gideri", "Ev Kredisi Taksiti",
                                      "--- Aylık Harcamalar ---",
                                      "Aylık Harcama Sepeti (Kütüphaneden)"], 
                                      key=f'debt_type_{context}')
            
            is_faizli_borc_ve_ek_odemeli = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Kredi (Sabit Taksit)", "Diğer Faizli Borç"]
            
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
                    debt_priority_str = st.selectbox("Ek Ödeme Sırası", options=secenekler, index=len(secenekler)-1,
                                                     help="Bu borcun, mevcut borçlara göre ek ödeme sırası neresi olmalı?", key=f'priority_select_{context}')
                else:
                    st.info("İlk ek ödemeye açık borcunuz bu olacak.")
                    debt_priority_str = "1. En Yüksek Öncelik (Her Şeyden Önce)"

        # --- YENİ DİNAMİK YAPI: Sadece Seçilen Borç Tipine Ait Alanlar Gösterilecek ---
        
        if debt_type == "Kredi Kartı":
            with col_f2:
                st.info("Kredi Kartı Detayları")
                kk_limit = st.number_input("Kart Limiti", min_value=1.0, value=150000.0, key=f'kk_limit_{context}')
                kk_kalan_ekstre = st.number_input("Kalan Ekstre Borcu (Faizli)", min_value=0.0, value=30000.0, key=f'kk_ekstre_{context}')
                kk_donem_ici = st.number_input("Dönem İçi İşlemler", min_value=0.0, value=5000.0, key=f'kk_donem_ici_{context}')
                initial_faizli_tutar = kk_kalan_ekstre + kk_donem_ici
            with col_f3:
                st.info("Taksit ve Faiz Bilgileri")
                debt_taksit = st.number_input("Gelecek Dönem Taksitleri (Aylık)", min_value=0.0, value=7000.0, key=f'kk_taksit_aylik_{context}')
                max_taksit_ay_kk = st.session_state.tr_params['kk_taksit_max_ay']
                debt_kalan_ay = st.number_input("Taksitlerin Kalan Ayı", min_value=0, max_value=max_taksit_ay_kk, value=min(12, max_taksit_ay_kk), key=f'kk_taksit_kalan_ay_{context}')
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=st.session_state.tr_params['kk_aylik_akdi_faiz'], step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
                debt_kk_asgari_yuzdesi = st.number_input("KK Asgari Ödeme Yüzdesi (%)", value=st.session_state.tr_params['kk_asgari_odeme_yuzdesi_default'], step=1.0, min_value=0.0, key=f'kk_asgari_{context}') / 100.0

        elif debt_type == "Ek Hesap (KMH)":
            with col_f2:
                st.info("Ek Hesap (KMH) Detayları")
                kmh_limit = st.number_input("Ek Hesap Limiti", min_value=1.0, value=50000.0, key=f'kmh_limit_{context}')
                initial_faizli_tutar = st.number_input("Kullanılan Anapara Tutarı", min_value=0.0, value=15000.0, key=f'initial_tutar_{context}')
            with col_f3:
                st.info("Faiz Bilgileri")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=st.session_state.tr_params['kmh_aylik_faiz'], step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
                debt_zorunlu_anapara_yuzdesi = st.number_input("Zorunlu Anapara Kapama Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key=f'kmh_anapara_{context}') / 100.0

        elif debt_type == "Kredi (Sabit Taksit)":
            with col_f2:
                st.info("Kredi Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=0.0, value=50000.0, key=f'initial_tutar_{context}')
                debt_taksit = st.number_input("Aylık Taksit Tutarı", min_value=0.0, value=5000.0, key=f'sabit_taksit_{context}')
            with col_f3:
                st.info("Vade ve Faiz")
                max_taksit_ay_kredi = st.session_state.tr_params['kredi_taksit_max_ay']
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=0, max_value=max_taksit_ay_kredi, value=min(24, max_taksit_ay_kredi), key=f'kalan_taksit_ay_{context}')
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=4.5, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0

        elif debt_type == "Diğer Faizli Borç":
            with col_f2:
                st.info("Borç Detayları")
                initial_faizli_tutar = st.number_input("Kalan Anapara Tutarı", min_value=0.0, value=10000.0, key=f'initial_tutar_{context}')
            with col_f3:
                st.info("Faiz Bilgisi")
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}') / 100.0
        
        elif debt_type in ["Sabit Kira Gideri", "Ev Kredisi Taksiti"]:
            with col_f2:
                st.info("Sabit Gider Detayları")
                debt_taksit = st.number_input("Aylık Gider Tutarı", min_value=0.0, value=15000.0 if debt_type == "Sabit Kira Gideri" else 25000.0, key=f'sabit_gider_tutar_{context}')
            with col_f3:
                devam_etme_yuzdesi_input = st.number_input("Gider Bitince Devam Yüzdesi (%)", value=0.0, min_value=0.0, max_value=100.0, step=1.0, key=f'devam_yuzdesi_{context}', help="Ev kredisi gibi süreli bir gider bittiğinde, bu tutarın yüzde kaçı normal harcama olarak devam etsin?") / 100.0
        
        elif debt_type == "Aylık Harcama Sepeti (Kütüphaneden)":
            with col_f2:
                st.info("Harcama Kalemlerini Seçin")
                df_harcama = st.session_state.harcama_kalemleri_df
                kalem_isimleri = df_harcama['Kalem Adı'].tolist()
                secilen_kalemler = st.multiselect("Sepete Eklenecek Kalemler", options=kalem_isimleri, default=kalem_isimleri, key=f'harcama_multiselect_{context}')
                
                toplam_tutar = df_harcama[df_harcama['Kalem Adı'].isin(secilen_kalemler)]['Aylık Bütçe (TL)'].sum() if secilen_kalemler else 0.0
                st.markdown(f"**Toplam Aylık Harcama:**")
                debt_taksit = st.number_input("Toplam Aylık Harcama", min_value=0.0, value=float(toplam_tutar), key=f'sabit_taksit_sepet_{context}', disabled=True, label_visibility="collapsed")
                harcama_kalemleri_isim = ", ".join(secilen_kalemler)
            with col_f3:
                 st.markdown(" ")
                 devam_etme_yuzdesi_input = 1.0 
        
        submit_button = st.form_submit_button(label="Borç/Gider Ekle")
        
        if submit_button:
            if debt_type == "Aylık Harcama Sepeti (Kütüphaneden)" and not harcama_kalemleri_isim:
                 st.error("Harcama Sepeti için en az bir kalem seçmelisiniz.")
                 return
            
            final_debt_name = f"{debt_name} ({harcama_kalemleri_isim})" if debt_type == "Aylık Harcama Sepeti (Kütüphaneden)" else debt_name
            
            add_debt(
                isim=final_debt_name,
                faizli_anapara=initial_faizli_tutar,
                oncelik_str=debt_priority_str,
                borc_tipi=debt_type,
                sabit_taksit=debt_taksit,
                kalan_ay=debt_kalan_ay,
                faiz_aylik=debt_faiz_aylik,
                kk_asgari_yuzdesi=debt_kk_asgari_yuzdesi,
                zorunlu_anapara_yuzdesi=debt_zorunlu_anapara_yuzdesi,
                kk_limit=kk_limit,
                devam_etme_yuzdesi=devam_etme_yuzdesi_input
            )


# --- Diğer Fonksiyonlar ve Kodun Geri Kalanı Aynen Kalır ---
# (Aşağıdaki kod önceki düzeltilmiş versiyonla aynıdır)

def display_and_manage_debts():
    if st.session_state.borclar:
        st.subheader("📊 Mevcut Borçlar ve Giderler")
        
        display_df = pd.DataFrame(st.session_state.borclar)
        
        cols_to_show = ['isim', 'min_kural', 'tutar', 'sabit_taksit', 'faiz_aylik', 'oncelik']
        display_df_filtered = display_df[[col for col in cols_to_show if col in display_df.columns]]
        
        display_df_filtered.columns = ["Yükümlülük Adı", "Kural", "Kalan Anapara", "Aylık Taksit/Gider", "Aylık Faiz (%)", "Öncelik"]
        
        display_df_filtered['Kalan Anapara'] = display_df_filtered['Kalan Anapara'].apply(format_tl)
        display_df_filtered['Aylık Taksit/Gider'] = display_df_filtered['Aylık Taksit/Gider'].apply(format_tl)
        display_df_filtered['Aylık Faiz (%)'] = (display_df_filtered['Aylık Faiz (%)'] * 100).apply(lambda x: f"{x:.2f}%")
        
        st.dataframe(
            display_df_filtered,
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
        
        if st.button("Seçili Borç/Gideri Sil", type="secondary"):
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

def simule_borc_planı(borclar_initial, gelirler_initial, **sim_params):
    
    if not borclar_initial or not gelirler_initial:
        return None

    st.session_state.tek_seferlik_gelir_isaretleyicisi.clear()

    mevcut_borclar = copy.deepcopy(borclar_initial)
    mevcut_gelirler = copy.deepcopy(gelirler_initial)
    
    ay_sayisi = 0
    mevcut_birikim = sim_params.get('baslangic_birikim', 0.0)
    birikime_ayrilan = sim_params.get('aylik_zorunlu_birikim', 0.0)
    faiz_carpani = sim_params.get('faiz_carpani', 1.0)
    agresiflik_carpan = sim_params.get('agresiflik_carpan', 1.0)
    birikim_artis_aylik = sim_params.get('birikim_artis_aylik', 0.0) / 12 / 100
    
    toplam_faiz_maliyeti = 0.0
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    
    aylik_sonuclar = []
    
    ilk_ay_toplam_gelir = 0
    ilk_ay_toplam_gider = 0

    while any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']) or ay_sayisi < 1:
        ay_sayisi += 1
        ay_adi = f"Ay {ay_sayisi}"
        
        toplam_gelir = 0.0
        for gelir in mevcut_gelirler:
            if ay_sayisi >= gelir['baslangic_ay']:
                if gelir['tek_seferlik']:
                    if ay_sayisi == gelir['baslangic_ay']:
                        toplam_gelir += gelir['tutar']
                else:
                    artis_carpan = (1 + gelir['artis_yuzdesi']) ** ((ay_sayisi - gelir['baslangic_ay']) / 12)
                    toplam_gelir += gelir['tutar'] * artis_carpan

        zorunlu_gider_toplam = birikime_ayrilan
        min_borc_odeme_toplam = 0.0
        
        aktif_borclar = []
        for borc in mevcut_borclar:
            if borc.get('kalan_ay', 999) > 0:
                 aktif_borclar.append(borc)
                 if borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                     borc['kalan_ay'] -= 1
        mevcut_borclar = aktif_borclar

        for borc in mevcut_borclar:
            min_odeme = hesapla_min_odeme(borc, faiz_carpani)
            if borc['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                zorunlu_gider_toplam += min_odeme
            else:
                min_borc_odeme_toplam += min_odeme

        if ay_sayisi == 1:
            ilk_ay_toplam_gelir = toplam_gelir
            ilk_ay_toplam_gider = zorunlu_gider_toplam + min_borc_odeme_toplam

        kalan_nakit = toplam_gelir - zorunlu_gider_toplam - min_borc_odeme_toplam
        saldırı_gucu = max(0, kalan_nakit * agresiflik_carpan)

        for borc in mevcut_borclar:
            if borc.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']:
                if borc['tutar'] > 0:
                    etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                    eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani
                    toplam_faiz_maliyeti += eklenen_faiz
                    borc['tutar'] += eklenen_faiz
                    borc['tutar'] -= hesapla_min_odeme(borc, faiz_carpani)
        
        saldırı_kalan = saldırı_gucu
        
        # Önceliklendirme
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
        
        mevcut_birikim += saldırı_kalan
        mevcut_birikim *= (1 + birikim_artis_aylik)

        aylik_sonuclar.append({
            'Ay': ay_adi, 'Toplam Gelir': round(toplam_gelir),
            'Toplam Zorunlu Giderler': round(zorunlu_gider_toplam),
            'Min. Borç Ödemeleri': round(min_borc_odeme_toplam),
            'Ek Ödeme Gücü': round(saldırı_gucu),
            'Aylık Birikim Katkısı': round(birikime_ayrilan + saldırı_kalan),
            'Kapanan Borçlar': ", ".join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(sum(b['tutar'] for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])),
            'Toplam Birikim': round(mevcut_birikim)
        })

        if ay_sayisi > 360:
            st.warning("‼️ Simülasyon 30 yılı aştığı için durduruldu.")
            break
            
    if ay_sayisi == 1 and not any(b['tutar'] > 1 for b in mevcut_borclar if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']):
        return {"df": pd.DataFrame(aylik_sonuclar), "ay_sayisi": 1, "toplam_faiz": round(toplam_faiz_maliyeti), "toplam_birikim": round(mevcut_birikim), "baslangic_faizli_borc": round(baslangic_faizli_borc), "ilk_ay_gelir": ilk_ay_toplam_gelir, "ilk_ay_gider": ilk_ay_toplam_gider, "limit_asimi": False}

    return {"df": pd.DataFrame(aylik_sonuclar), "ay_sayisi": ay_sayisi, "toplam_faiz": round(toplam_faiz_maliyeti), "toplam_birikim": round(mevcut_birikim), "baslangic_faizli_borc": round(baslangic_faizli_borc), "ilk_ay_gelir": ilk_ay_toplam_gelir, "ilk_ay_gider": ilk_ay_toplam_gider, "limit_asimi": False}


# --- 7. Ana Uygulama Düzeni ---
st.title("Borç Kapatma ve Finansal Planlama Simülasyonu")
# ... (Kodun geri kalanı aynı)
# (Kısaltma amacıyla buraya eklenmedi, önceki kod bloğundaki gibi devam ediyor)
# --- 7. Ana Uygulama Düzeni ---

st.title("Borç Kapatma ve Finansal Planlama Simülasyonu")

tab_basic, tab_advanced, tab_rules = st.tabs(["✨ Basit Planlama (Başlangıç)", "🚀 Gelişmiş Planlama", "⚙️ Yönetici Kuralları"])

# --- TAB 2: Basit Planlama (Öne alındı ve açıklamalar eklendi) ---
with tab_basic:
    st.header("✨ Hızlı ve Varsayılan Planlama")
    
    st.markdown("---")
    st.header("🚀 Programın Amacı: Borçlarınızı En Hızlı ve En Ucuz Yolla Kapatın")
    
    st.info("""
        Bu simülasyon, borçlarınızı kapatma sürecini **stratejik ve sayısal** bir yaklaşımla planlar.
        
        Amacımız: **Mevcut gelir ve giderlerinizle borçlarınızı ne kadar sürede kapatabilir, bu süreçte ne kadar faiz öder ve ne kadar birikim yapabilirsiniz?** sorularına kesin cevaplar sunmaktır.
        
        Planlama başlarken: **1. Gelirleri, 2. Borç/Giderleri girin** ve ardından **3. Planınızı Oluşturun.**
    """)
    
    with st.expander("📄 Detaylı Kullanım Kılavuzunu Gör"):
        st.subheader("Adım 1: Gelir ve Borçları/Giderleri Tanımlama")
        st.markdown("""
        1. **Gelir Kaynağı:** Net aylık gelirinizi ve beklenen **Yıllık Artış Yüzdesini** (örn. %10) girin. Tek seferlik bonusları da eklemeyi unutmayın.
        2. **Borçlar ve Giderler:** Tüm sabit giderlerinizi (Kira, Harcama Sepeti, KK Taksitleri) ve faizli borçlarınızı (KK Dönem Borcu, Kredi, KMH) ekleyin. Program, **BDDK yasal faiz ve taksit kısıtlarını** dikkate alır.
        """)
        
        st.subheader("Adım 2: Stratejinizi Seçin (Varsayılanlar)**")
        varsayilan_agresiflik_str = st.session_state.get('default_agressiflik', 'Maksimum Çaba (Tüm Ek Ödeme)')
        varsayilan_oncelik_str = st.session_state.get('default_oncelik', 'Borç Çığı (Avalanche - Önce Faiz)')
        st.markdown(f"""
        * **Ek Ödeme Agresifliği:** Varsayılan olarak **{varsayilan_agresiflik_str}** kullanılır. (Kalan paranın tamamını borca yönlendirir.)
        * **Borç Kapatma Yöntemi:** Varsayılan olarak **{varsayilan_oncelik_str}** kullanılır (En yüksek faize öncelik, en çok faiz tasarrufu).
        """)
        
        st.subheader("Adım 3: Sonuçları Değerlendirme")
        st.markdown("""
        Simülasyon size **Borç Kapanma Süresini**, **Toplam Ödenen Faiz Maliyetini** ve **Kapanış Anındaki Toplam Birikim** miktarınızı net olarak gösterecektir.
        
        Daha detaylı senaryolar (Faiz Oranı Çarpanı, Manuel Sıra) için **'🚀 Gelişmiş Planlama'** sekmesini kullanın.
        """)
        
        st.markdown("Kuralları, faiz oranlarını ve harcama bütçenizi değiştirmek için **'⚙️ Yönetici Kuralları'** sekmesini kullanın.")
    
    st.markdown("---")

    varsayilan_agresiflik_str = st.session_state.get('default_agressiflik', 'Maksimum Çaba (Tüm Ek Ödeme)')
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
        with st.expander("❓ Faiz Çarpanı Ne İşe Yarar?"):
            st.markdown("""
                Bu çarpan, girdiğiniz tüm faiz oranlarını test amaçlı artırmanıza veya azaltmanıza olanak tanır.
                
                * **1.0'dan Büyük Değerler (Örn: 1.2x):** **Risk Analizi** - Faizler artarsa borç süreniz ve maliyetiniz ne olur?
                * **1.0'dan Küçük Değerler (Örn: 0.8x):** **Fırsat Analizi** - Yapılandırma veya borç transferi ile faizi düşürmenin size ne kazandırdığını görün.
            """)
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
                    {'isim': b['isim'], 'mevcut_oncelik': b['oncelik'] - 1000 if b['oncelik'] > 999 else b['oncelik'], 'yeni_oncelik': b['oncelik'] - 1000 if b['oncelik'] > 999 else b['oncelik']}
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
        varsayilan_agresiflik_str = st.session_state.get('default_agressiflik', 'Maksimum Çaba (Tüm Ek Ödeme)')
        varsayilan_oncelik_str = st.session_state.get('default_oncelik', 'Borç Çığı (Avalanche - Önce Faiz)')
        
        sim_params = {
            'agresiflik_carpan': STRATEJILER[varsayilan_agresiflik_str],
            'oncelik_stratejisi': ONCELIK_STRATEJILERI[varsayilan_oncelik_str],
            'faiz_carpani': 1.0,
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
