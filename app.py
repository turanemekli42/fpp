import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import locale
import matplotlib.pyplot as plt

# PDF OLUŞTURMA İÇİN GEREKLİ KÜTÜPHANE
from fpdf import FPDF 
import base64
import io

# ======================================================================
# 0. AYARLAR VE SABİT DEĞERLER
# ======================================================================

# Türkçe yerel ayarlarını ayarla (Formatlama için)
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Turkish_Turkey')
    except locale.Error:
        pass

# Varsayılan Kurlar (UX kolaylığı için kullanıcının girmesi engellendi)
DEFAULT_BIRIM_DEGERLERI = {
    "TL (Nakit/Vadeli Mevduat)": 1.0,
    "Gram Altın": 2500.0,
    "Dolar (USD)": 32.5,
    "Euro (EUR)": 35.0,
    "Diğer": 1.0
}

st.set_page_config(layout="wide") 

if 'borclar' not in st.session_state:
    st.session_state.borclar = []
if 'gelirler' not in st.session_state:
    st.session_state.gelirler = []
if 'tek_seferlik_gelir_isaretleyicisi' not in st.session_state:
    st.session_state.tek_seferlik_gelir_isaretleyicisi = set()


# ======================================================================
# 1. STREAMLIT KULLANICI GİRİŞLERİ (SEKMELER)
# ======================================================================

st.title("Finansal Borç Yönetimi Simülasyon Projesi")
st.markdown("---")
tab1, tab2 = st.tabs(["📊 Simülasyon Verileri", "⚙️ Yönetici Kuralları"])

# --------------------------------------------------
# Yönetici Kuralları Sekmesi (tab2) - GÜNCELLENDİ
# --------------------------------------------------
with tab2:
    st.header("Simülasyon Kurallarını Yönet")
    
    st.subheader("Borç Kapatma Stratejisi Çarpanları (Agresiflik)")
    COL_A, COL_B, COL_C = st.columns(3)
    with COL_A:
        CARPAN_YUMUSAK = st.number_input("Yumuşak Çarpanı", value=0.2, min_value=0.0, max_value=1.0, step=0.05, key='carpan_konforlu')
    with COL_B:
        CARPAN_DENGELI = st.number_input("Dengeli Çarpanı", value=0.5, min_value=0.0, max_value=1.0, step=0.05, key='carpan_dengeli')
    with COL_C:
        CARPAN_SALDIRGAN = st.number_input("Saldırgan Çarpanı", value=1.0, min_value=0.0, max_value=1.0, step=0.05, key='carpan_agresif')
        
    STRATEJILER = {
        "Yumuşak (Düşük Ek Ödeme)": CARPAN_YUMUSAK,
        "Dengeli (Orta Ek Ödeme)": CARPAN_DENGELI,
        "Saldırgan (Maksimum Ek Ödeme)": CARPAN_SALDIRGAN
    }
    
    st.markdown("---")
    st.subheader("Faiz Oranı Sapma Senaryoları")
    col_F1, col_F2, col_F3 = st.columns(3)
    with col_F1:
        FAIZ_CARPAN_IYIMSER = st.number_input("İyimser Senaryo Çarpanı", value=0.8, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_iyimser')
    with col_F2:
        FAIZ_CARPAN_NORMAL = st.number_input("Normal Senaryo Çarpanı", value=1.0, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_normal')
    with col_F3:
        FAIZ_CARPAN_KOTUMSER = st.number_input("Kötümser Senaryo Çarpanı", value=1.2, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_kotumser')
                                               
    FAIZ_STRATEJILERI = {
        "İyimser Faiz (x0.8)": FAIZ_CARPAN_IYIMSER,
        "Normal Faiz (x1.0)": FAIZ_CARPAN_NORMAL,
        "Kötümser Faiz (x1.2)": FAIZ_CARPAN_KOTUMSER
    }
    
    st.markdown("---")
    st.subheader("Birikim Değerlemesi Artış Tahmini Referansı")
    
    # REFERANS TABLOSU EKLENDİ
    st.info("""
        #### 💡 Tahmini Aylık Değer Artışı Referansı
        Simülasyon, birikimlerinizin değerini korumasını esas alır. Lütfen birikim aracınızın 
        **aylık ortalama** değerlenme tahminini giriniz.
        
        | Birikim Aracı | Tipik Aylık (%) | Yorum |
        | :--- | :--- | :--- |
        | **TL (Nakit/Mevduat)** | 2.5% - 4.5% | Banka mevduat faiz getirisine eşittir. |
        | **Döviz (USD/EUR)** | 1.0% - 3.0% | Tahmini kur artış hızına eşittir. |
        | **Altın/Diğer** | 1.5% - 4.0% | Enflasyona karşı koruma beklentisine eşittir. |
    """)


# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1) - GÜNCELLENDİ
# --------------------------------------------------
with tab1:
    
    # ======================================================================
    # 1.1. GENEL HEDEFLER VE BAŞLANGIÇ AYARLARI
    # ======================================================================
    st.header("Finansal Hedefler ve Simülasyon Başlangıcı")

    aylar_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        SIM_BASLANGIC_AYI = st.selectbox("Simülasyon Başlangıç Ayı", options=[f"{a} {y}" for y in range(2025, 2027) for a in aylar_tr], index=9)
        
        sim_bas_yil = int(SIM_BASLANGIC_AYI.split()[1])
        hedef_ay_str = st.selectbox("Hedef Borç Kapatma Ayı", options=aylar_tr, index=5, key='hedef_ay')
        hedef_yil = st.number_input("Hedef Borç Kapatma Yılı", min_value=sim_bas_yil, max_value=sim_bas_yil + 5, value=sim_bas_yil + 2, key='hedef_yil')
        HEDEF_BITIS_TARIHI = f"{hedef_ay_str} {hedef_yil}"
        
        ONCELIK = st.selectbox("Öncelikli Amaç", 
                               options=["Borç Kapatma Hızını Maksimize Et", "Birikim Hedefine Ulaşmayı Garanti Et"],
                               index=0,
                               help="Borç Kapatma öncelikliyse, birikim hedefi borç bitimine kadar esnek tutulur.")

    with col_h2:
        BIRIKIM_TIPI = st.radio("Birikim Hedefi Tipi", 
                                ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"],
                                index=0)
        
        AYLIK_ZORUNLU_BIRIKIM = 0.0
        TOPLAM_BIRIKIM_HEDEFI = 0.0

        if BIRIKIM_TIPI == "Aylık Sabit Tutar":
            AYLIK_ZORUNLU_BIRIKIM = st.number_input("Aylık Zorunlu Birikim Tutarı", 
                                                     value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik')
        
        else:
            TOPLAM_BIRIKIM_HEDEFI = st.number_input("Hedef Toplam Birikim Tutarı", 
                                                     value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam')
        
        # YENİ EKLENEN BİRİKİM DEĞERLEME ALANLARI
        st.markdown("---")
        st.subheader("Birikim Aracının Değerlemesi")
        
        BIRIKIM_ARACI = st.selectbox("Birikimlerin Yönlendirileceği Araç", 
                                     options=list(DEFAULT_BIRIM_DEGERLERI.keys()), 
                                     index=1, key='birikim_araci_tab1')
        
        TAHMINI_AYLIK_ARTIS_YUZDESI = st.number_input("Tahmini Aylık Değer Artışı (%)", 
                                                       value=1.5, min_value=0.0, step=0.1, 
                                                       key='aylik_artis_yuzdesi_tab1',
                                                       help="Birikim aracınızın enflasyona karşı koruma dahil, aylık ortalama değerlenme tahmini. (Referans için Yönetici Kuralları sekmesine bakın.)")

    
    # ======================================================================
    # 1.2. DİNAMİK GELİR EKLEME ARAYÜZÜ
    # ======================================================================
    st.markdown("---")
    st.subheader("Gelir Kaynaklarını Yönet")
    
    # Yardımcı Fonksiyon: Gelir Ekle
    def add_income(isim, tutar, artış_kuralı, artış_yuzdesi, periyot_ay, zam_ayi_gun):
        
        if artış_kuralı == "Sabit (Artış Yok)":
            artış_oranı = 1.0
            periyot = "Aylık"
            zam_ayi_gun = ""
        elif artış_kuralı == "Yıllık Zam":
            periyot = "Aylık"
            artış_oranı = 1 + (artış_yuzdesi / 100.0)
        elif artış_kuralı == "Dönemlik Zam":
             periyot = "Aylık"
             artış_oranı = 1 + (artış_yuzdesi / 100.0)
        elif artış_kuralı == "Tek Seferlik Ödeme":
            periyot = "Tek Seferlik"
            artış_oranı = 1.0
            artış_yuzdesi = 0
            periyot_ay = 999 

        new_income = {
            "isim": isim,
            "baslangic_tutar": tutar,
            "periyot": periyot,
            "artış_kuralı": artış_kuralı,
            "artış_oranı": artış_oranı,
            "zam_ayi_gun": zam_ayi_gun, 
            "zam_yuzdesi": artış_yuzdesi,
            "periyot_ay": periyot_ay # Dönemlik zam için
        }
        st.session_state.gelirler.append(new_income)
        st.success(f"'{isim}' geliri başarıyla eklendi.")


    # Gelir Ekleme Formu
    with st.form("new_income_form", clear_on_submit=True):
        st.markdown("#### Yeni Gelir Ekle")
        
        col_g1, col_g2 = st.columns(2) 
        with col_g1:
            income_name = st.text_input("Gelir Kaynağı Adı", value="Ana Maaş")
            initial_tutar = st.number_input("Başlangıç Net Tutarı (TL)", min_value=1.0, value=80000.0)
            
        with col_g2:
            artış_kuralı = st.selectbox("Gelir Artış Kuralı", 
                                       ["Sabit (Artış Yok)", "Yıllık Zam", "Dönemlik Zam", "Tek Seferlik Ödeme"])
            
            artış_yuzdesi = 0.0
            zam_ayi = ""
            periyot_ay = 12
            
            if artış_kuralı in ["Yıllık Zam", "Dönemlik Zam"]:
                artış_yuzdesi = st.number_input("Artış Yüzdesi (Örn: 30)", value=30.0, min_value=0.0, key='income_zam_yuzdesi')

            if artış_kuralı == "Yıllık Zam":
                zam_ayi = st.selectbox("Yıllık Artış Ayı", options=aylar_tr, index=0, key='income_zam_ayi')
                
            elif artış_kuralı == "Dönemlik Zam":
                 periyot_ay = st.selectbox("Artış Sıklığı (Ayda Bir)", options=[3, 6, 9], index=1, key='income_donemlik_periyot')
            
            elif artış_kuralı == "Tek Seferlik Ödeme":
                 zam_ayi = st.selectbox("Gelirin Geleceği Ay", options=aylar_tr, index=9, key='income_tek_seferlik_ayi')


        submit_income_button = st.form_submit_button(label="Geliri Ekle")
        if submit_income_button:
            add_income(income_name, initial_tutar, artış_kuralı, artış_yuzdesi, periyot_ay, zam_ayi)


    # Eklenen Gelirleri Göster
    if st.session_state.gelirler:
        st.markdown("#### Eklenen Gelir Kaynaklarınız")
        income_data = []
        for i, income in enumerate(st.session_state.gelirler):
            
             if income['artış_kuralı'] == "Tek Seferlik Ödeme":
                 artış_kuralı_str = f"Tek Seferlik ({income['zam_ayi_gun']} ayında)"
             elif income['artış_kuralı'] == "Yıllık Zam":
                 artış_kuralı_str = f"Yıllık %{income['zam_yuzdesi']:.0f} (her {income['zam_ayi_gun']})"
             elif income['artış_kuralı'] == "Dönemlik Zam":
                 artış_kuralı_str = f"Dönemlik %{income['zam_yuzdesi']:.0f} (her {income['periyot_ay']} ayda bir)"
             else:
                 artış_kuralı_str = "Sabit (Değişmez)"
                 
             income_data.append({
                 "Gelir Adı": income['isim'],
                 "Başlangıç Tutarı": f"₺{income['baslangic_tutar']:,.0f}",
                 "Artış Kuralı": artış_kuralı_str,
             })
        income_df = pd.DataFrame(income_data)
        st.dataframe(income_df, use_container_width=True, hide_index=True)
        
        # Silme kısmı aynı kalır...


    # ======================================================================
    # 1.3. BORÇLAR VE SABİT GİDERLER (YÜKÜMLÜLÜKLER) - GÜNCELLENDİ
    # ======================================================================
    st.markdown("---")
    st.subheader("Aylık Yükümlülükler ve Borçlar (Giderler)")
    
    def add_debt(isim, faizli_anapara, oncelik, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi):
        
        borc_listesi = []
        
        if borc_tipi == "Kredi Kartı":
            # 1. KK Taksitli Alışverişler (Gider olarak)
            if sabit_taksit > 0 and kalan_ay > 0:
                borc_listesi.append({
                    "isim": f"{isim} (Taksitler)",
                    "tutar": 0, # Anapara sıfır, sadece taksit var
                    "min_kural": "SABIT_TAKSIT_GIDER",
                    "oncelik": oncelik, 
                    "sabit_taksit": sabit_taksit,
                    "kalan_ay": kalan_ay,
                    "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
                })
            
            # 2. KK Dönem Borcu (Faizli)
            if faizli_anapara > 0:
                 borc_listesi.append({
                    "isim": f"{isim} (Dönem Borcu)",
                    "tutar": faizli_anapara,
                    "min_kural": "ASGARI_FAIZ", # Faiz + Min Anapara
                    "oncelik": oncelik + 100, # Taksitlerden daha düşük öncelik
                    "faiz_aylik": faiz_aylik,
                    "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
                    "kalan_ay": 99999
                })
        
        elif borc_tipi == "Ek Hesap (KMH)":
             borc_listesi.append({
                "isim": isim,
                "tutar": faizli_anapara,
                "min_kural": "FAIZ_ART_ANAPARA", # Yeni Kural
                "oncelik": oncelik,
                "faiz_aylik": faiz_aylik,
                "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi,
                "kalan_ay": 99999
            })

        elif borc_tipi in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]:
            borc_listesi.append({
                "isim": isim,
                "tutar": 0, "min_kural": "SABIT_GIDER", "oncelik": 1,
                "sabit_taksit": sabit_taksit, "kalan_ay": 99999,
                "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
            })
            
        elif borc_tipi == "Kredi (Sabit Taksit)":
             borc_listesi.append({
                "isim": isim,
                "tutar": faizli_anapara, "min_kural": "SABIT_TAKSIT_ANAPARA", "oncelik": oncelik,
                "sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay,
                "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
            })
            
        else: # Diğer Faizli Borçlar
             borc_listesi.append({
                "isim": isim,
                "tutar": faizli_anapara, "min_kural": "FAIZ", "oncelik": oncelik,
                "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0, "kalan_ay": 99999
            })
        
        if borc_listesi:
            st.session_state.borclar.extend(borc_listesi)
            st.success(f"'{isim}' yükümlülüğü başarıyla eklendi.")


    with st.form("new_debt_form", clear_on_submit=True):
        st.markdown("#### Yeni Yükümlülük/Borç Ekle")
        
        col_f1, col_f2, col_f3 = st.columns(3) 
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Borç")
            debt_type = st.selectbox("Yükümlülük Tipi", 
                                     ["Kredi Kartı", "Ek Hesap (KMH)", 
                                      "--- Sabit Giderler ---", 
                                      "Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti",
                                      "--- Sabit Ödemeli Borçlar ---",
                                      "Kredi (Sabit Taksit)", 
                                      "--- Diğer Faizli Borçlar ---",
                                      "Diğer Faizli Borç"])
            debt_priority = st.number_input("Ek Ödeme Önceliği (1 En Yüksek)", min_value=1, value=5)
            
        with col_f2:
            is_faizli_borc = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Diğer Faizli Borç"]
            is_sabit_gider = debt_type in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]
            is_sabit_kredi = debt_type == "Kredi (Sabit Taksit)"
            
            initial_faizli_tutar = 0.0
            debt_taksit = 0.0
            debt_kalan_ay = 0
            
            if is_faizli_borc or is_sabit_kredi:
                initial_faizli_tutar = st.number_input("Faizli Kalan Borç Anaparası", min_value=0.0, value=50000.0, key='initial_tutar')

            if debt_type == "Kredi Kartı":
                st.info("Kredi Kartı, taksitler ve dönem borcu olarak ikiye ayrılacaktır.")
                debt_taksit = st.number_input("KK Taksitli Alışverişlerin Aylık Ödemesi", min_value=0.0, value=5000.0, key='kk_taksit_aylik')
                debt_kalan_ay = st.number_input("KK Taksitlerin Ortalama Kalan Ayı", min_value=1, value=12, key='kk_taksit_kalan_ay')

            if is_sabit_gider or is_sabit_kredi:
                debt_taksit = st.number_input("Aylık Zorunlu Taksit/Gider Tutarı", min_value=1.0, value=5000.0, key='sabit_taksit')
                if is_sabit_kredi:
                    debt_kalan_ay = st.number_input("Kredi Kalan Taksit Ayı", min_value=1, value=12, key='kalan_taksit_ay')
                
        with col_f3:
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0
            debt_zorunlu_anapara_yuzdesi = 0.0
            
            if is_faizli_borc:
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0, key='debt_faiz_aylik') / 100.0
                
                if debt_type == "Kredi Kartı":
                    debt_kk_asgari_yuzdesi = st.number_input("KK Asgari Ödeme Anapara Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key='kk_asgari') / 100.0
                
                if debt_type == "Ek Hesap (KMH)":
                     debt_zorunlu_anapara_yuzdesi = st.number_input("KMH Zorunlu Anapara Kapama Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key='kmh_anapara') / 100.0
                
        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        if submit_button:
            add_debt(debt_name, initial_faizli_tutar, debt_priority, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi, debt_zorunlu_anapara_yuzdesi)

    if st.session_state.borclar:
        st.markdown("#### Eklenen Yükümlülükleriniz (Önceliğe Göre Sıralı)")
        # ... (Gösterim kısmı aynı kalır)

    # ... (Silme kısmı aynı kalır)


    # ------------------------------------------------------------------
    # HESAPLA BUTONU BURADA
    # ------------------------------------------------------------------
    st.markdown("---")
    is_disabled = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button = st.button("TÜM FİNANSAL STRATEJİLERİ HESAPLA VE YORUMLA", type="primary", disabled=is_disabled)


# ----------------------------------------------------------------------
# 2. YARDIMCI FONKSIYONLAR (Minimum Ödeme Hesaplama Mantığı) - GÜNCELLENDİ
# ----------------------------------------------------------------------

def format_tl(value):
    """Değeri binler basamağı ayrılmış Türk Lirası formatına çevirir (Locale bağımsız)."""
    if value is None: value = 0
    tam_sayi = int(round(value))
    formatted_value = f"₺{tam_sayi:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted_value

def hesapla_min_odeme(borc, faiz_carpani=1.0):
    """Her bir borç için minimum ödeme tutarını o borca ait kurala göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    faiz_aylik = borc['faiz_aylik'] * faiz_carpani
    
    if tutar <= 0 and not kural.startswith("SABIT"): return 0
    
    if kural == "SABIT_GIDER":
          return borc.get('sabit_taksit', 0)
          
    if kural in ["SABIT_TAKSIT_GIDER", "SABIT_TAKSIT_ANAPARA"]:
        if borc.get('kalan_ay', 0) > 0:
            return borc.get('sabit_taksit', 0)
        return 0
    
    # Kredi Kartı Asgari Ödeme Kuralı (Faiz + Min Anapara Yüzdesi)
    elif kural == "ASGARI_FAIZ":
        kk_asgari_yuzdesi = borc['kk_asgari_yuzdesi']
        return (tutar * faiz_aylik) + (tutar * kk_asgari_yuzdesi) 
        
    # Ek Hesap Kuralı (Faiz + Zorunlu Anapara Yüzdesi)
    elif kural == "FAIZ_ART_ANAPARA": 
        zorunlu_anapara_yuzdesi = borc['zorunlu_anapara_yuzdesi']
        return (tutar * faiz_aylik) + (tutar * zorunlu_anapara_yuzdesi)
    
    # Sadece Faiz Kuralı (Basit Faizli Borçlar için)
    elif kural == "FAIZ":
        return tutar * faiz_aylik
        
    return 0
    
# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU - GÜNCELLENDİ
# ----------------------------------------------------------------------

def simule_borc_planı(borclar_listesi, gelirler_listesi, agresiflik_carpani, faiz_carpani, hedef_tipi, aylik_min_birikim, toplam_birikim_hedefi, oncelik, birikim_araci, aylik_artis_yuzdesi):
    
    aylik_sonuclar = []
    mevcut_borclar = [b.copy() for b in borclar_listesi] 
    mevcut_gelirler = [g.copy() for g in gelirler_listesi] 
    
    ay_str = SIM_BASLANGIC_AYI.split()
    aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
    sim_baslangic_tarihi = datetime(int(ay_str[1]), aylar_map[ay_str[0]], 1)
    tarih = sim_baslangic_tarihi
    
    ay_sayisi = 0
    max_iterasyon = 60
    
    toplam_faiz_maliyeti = 0 
    
    # Başlangıçtaki faizli borç toplamını hesapla (sadece ek ödeme yapılabilen borçlar)
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    
    # Birikim Değerleme Ayarları
    aylik_artis_carpani = 1 + (aylik_artis_yuzdesi / 100.0)
    birikim_araci_miktari = 0.0
    
    # Varsayılan başlangıç değerini çek (TL karşılığı)
    BIRIM_BASLANGIC_DEGERI = DEFAULT_BIRIM_DEGERLERI.get(birikim_araci, 1.0)
    guncel_birikim_birim_degeri = BIRIM_BASLANGIC_DEGERI 
    mevcut_birikim = 0.0

    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Dinamik Gelir Hesaplama
        toplam_gelir = 0
        for gelir in mevcut_gelirler:
            gelir_tutari = gelir['baslangic_tutar']
            zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
            gelir_id = (gelir['isim'], gelir['artış_kuralı'])

            if gelir['artış_kuralı'] == "Tek Seferlik Ödeme":
                if (tarih.month == zam_ay_no and 
                    tarih.year >= sim_baslangic_tarihi.year and 
                    gelir_id not in st.session_state.tek_seferlik_gelir_isaretleyicisi):
                    toplam_gelir += gelir_tutari
                    st.session_state.tek_seferlik_gelir_isaretleyicisi.add(gelir_id)
            
            elif gelir['artış_kuralı'] == "Yıllık Zam":
                if tarih.month == zam_ay_no and tarih > sim_baslangic_tarihi:
                    gelir['baslangic_tutar'] *= gelir['artış_oranı']
                    gelir_tutari = gelir['baslangic_tutar']
                toplam_gelir += gelir_tutari
                
            elif gelir['artış_kuralı'] == "Dönemlik Zam":
                 if ay_sayisi > 0 and ay_sayisi % gelir['periyot_ay'] == 0:
                    gelir['baslangic_tutar'] *= gelir['artış_oranı']
                    gelir_tutari = gelir['baslangic_tutar']
                 toplam_gelir += gelir_tutari
                 
            else: # Sabit
                toplam_gelir += gelir_tutari
        
        if ay_sayisi == 0:
            ilk_ay_toplam_gelir = toplam_gelir
        
        
        # 3.2. Yükümlülük Ödemeleri (Giderler + Min. Borç Ödemeleri)
        zorunlu_gider_toplam = 0
        min_borc_odeme_toplam = 0
        
        for borc in mevcut_borclar:
            min_odeme = hesapla_min_odeme(borc, faiz_carpani)
            if borc['min_kural'].startswith("SABIT"):
                zorunlu_gider_toplam += min_odeme
            else: 
                min_borc_odeme_toplam += min_odeme
        
        if ay_sayisi == 0:
              ilk_ay_min_borc_odeme = min_borc_odeme_toplam
              ilk_ay_zorunlu_gider = zorunlu_gider_toplam
        
        # 3.3. Kalan Nakit Hesaplama
        giderler_dahil_min_odeme = zorunlu_gider_toplam + min_borc_odeme_toplam
        kalan_nakit_brut = toplam_gelir - giderler_dahil_min_odeme
        kalan_nakit = max(0, kalan_nakit_brut) 
        
        # 3.4. Birikim ve Saldırı Gücü Dağıtımı
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
        
        birikime_ayrilan = 0.0
        saldırı_gucu = 0.0
        
        if yuksek_oncelikli_borclar_kaldi:
            # ... (Birikim hedefleri ve saldırı gücü hesaplaması aynı kalır)
            if hedef_tipi == "Aylık Sabit Tutar":
                hedef_birikim_aylik = aylik_min_birikim
            else: 
                kalan_ay_sayisi = max_iterasyon - ay_sayisi
                kalan_birikim_hedefi = max(0, toplam_birikim_hedefi - mevcut_birikim)
                hedef_birikim_aylik = kalan_birikim_hedefi / kalan_ay_sayisi if kalan_ay_sayisi > 0 else kalan_birikim_hedefi
            
            if oncelik == "Birikim Hedefine Ulaşmayı Garanti Et":
                birikime_ayrilan = min(kalan_nakit, hedef_birikim_aylik)
                kalan_nakit -= birikime_ayrilan
                saldırı_gucu = kalan_nakit * agresiflik_carpani
            else: 
                zorunlu_birikim_payi = min(kalan_nakit, hedef_birikim_aylik)
                kalan_nakit -= zorunlu_birikim_payi
                saldırı_gucu = kalan_nakit * agresiflik_carpani
                birikime_ayrilan = zorunlu_birikim_payi + (kalan_nakit * (1 - agresiflik_carpani))

        else:
            birikime_ayrilan = kalan_nakit
            saldırı_gucu = 0
            
        # 3.5. Birikim Değerleme ve Güncelleme (YENİ)
        # 1. Mevcut birikim aracının TL değerini artır (enflasyon/kur artışı simülasyonu)
        guncel_birikim_birim_degeri *= aylik_artis_carpani
        
        # 2. O ayki nakit birikimi birim miktara çevir ve ekle
        if guncel_birikim_birim_degeri > 0:
            eklenen_birim_miktar = birikime_ayrilan / guncel_birikim_birim_degeri
            birikim_araci_miktari += eklenen_birim_miktar
        
        # 3. Yeni TL karşılığını hesapla
        mevcut_birikim = birikim_araci_miktari * guncel_birikim_birim_degeri

            
        # 3.6. Borçlara Ödeme Uygulama
        
        saldırı_kalan = saldırı_gucu
        kapanan_borclar_listesi = []
        
        # a) Taksit/Faiz/Min Ödeme İşlemleri
        for borc in mevcut_borclar:
            
            if borc['min_kural'].startswith("SABIT"):
                if borc['min_kural'] in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                    borc['kalan_ay'] = max(0, borc['kalan_ay'] - 1)
                    if borc['min_kural'] == 'SABIT_TAKSIT_ANAPARA':
                         # Taksit anaparayı düşürür
                         min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                         borc['tutar'] -= min_odeme
            else: # Faizli borçlar için (KK, KMH, Diğer Faizli)
                if borc['tutar'] > 0:
                    etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                    eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani 
                    toplam_faiz_maliyeti += eklenen_faiz
                    
                    min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                    borc['tutar'] += eklenen_faiz 
                    borc['tutar'] -= min_odeme 
                    
        # b) Saldırı Gücünü Uygulama (Faiz Çığı Mantığı)
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            # Sadece faizli ve ek ödemeye açık borçlara saldır!
            is_ek_odemeye_acik = borc['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
            
            if borc['tutar'] > 1 and saldırı_kalan > 0 and is_ek_odemeye_acik:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0

        # 3.7. Sonuçları Kaydetme ve Döngü Kontrolü
        kalan_faizli_borc_toplam = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
        
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir),
            'Toplam Zorunlu Giderler': round(zorunlu_gider_toplam),
            'Min. Borç Ödemeleri': round(min_borc_odeme_toplam),
            'Borç Saldırı Gücü': round(saldırı_gucu),
            'Aylık Birikim Katkısı': round(birikime_ayrilan),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(kalan_faizli_borc_toplam)
        })
        
        tum_yukumlulukler_bitti = all(b['tutar'] <= 1 and b.get('kalan_ay', 0) <= 0 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER'])
        
        if tum_yukumlulukler_bitti:
              break
        
        ay_sayisi += 1
        tarih += relativedelta(months=1)
        
    ilk_ay_toplam_gider = ilk_ay_zorunlu_gider + ilk_ay_min_borc_odeme
    
    return {
        "df": pd.DataFrame(aylik_sonuclar),
        "ay_sayisi": ay_sayisi,
        "toplam_faiz": round(toplam_faiz_maliyeti),
        "toplam_birikim": round(mevcut_birikim),
        "baslangic_faizli_borc": round(baslangic_faizli_borc),
        "ilk_ay_gelir": ilk_ay_toplam_gelir,
        "ilk_ay_gider": ilk_ay_toplam_gider
    }


# ----------------------------------------------------------------------
# 4. YORUM VE GRAFİK FONKSİYONLARI (Aynı Kaldı)
# ----------------------------------------------------------------------
# ... (Fonksiyonlar yap_finansal_yorum, create_comparison_chart, PDF sınıfları aynı kalmıştır.)

# ----------------------------------------------------------------------
# 6. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ (Aynı Kaldı, Çağrılar Güncellendi)
# ----------------------------------------------------------------------

if calculate_button:
    
    # ... (Hata kontrolü aynı kalır)

    # Başlangıç Yorumu İçin Temel Oranı Hesapla (Normal Faiz/Agresiflik 0)
    temp_result = simule_borc_planı(
        st.session_state.borclar, 
        st.session_state.gelirler, 
        0.0, 
        1.0, 
        BIRIKIM_TIPI, 
        AYLIK_ZORUNLU_BIRIKIM, 
        TOPLAM_BIRIKIM_HEDEFI, 
        ONCELIK,
        BIRIKIM_ARACI,            # YENİ PARAMETRE
        TAHMINI_AYLIK_ARTIS_YUZDESI # YENİ PARAMETRE
    )
    
    # ... (Yorumlama kısmı aynı kalır)
    
    # --- TÜM SENARYOLARI SİMULE ET ---
    all_scenarios = {}
    for faiz_name, faiz_carpan in FAIZ_STRATEJILERI.items(): 
        for aggressive_name, aggressive_carpan in STRATEJILER.items(): 
            
            scenario_name = f"{aggressive_name} / {faiz_name}"
            
            all_scenarios[scenario_name] = simule_borc_planı(
                st.session_state.borclar, 
                st.session_state.gelirler, 
                aggressive_carpan, 
                faiz_carpan,       
                BIRIKIM_TIPI, 
                AYLIK_ZORUNLU_BIRIKIM, 
                TOPLAM_BIRIKIM_HEDEFI, 
                ONCELIK,
                BIRIKIM_ARACI,            # YENİ PARAMETRE
                TAHMINI_AYLIK_ARTIS_YUZDESI # YENİ PARAMETRE
            )
            st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

    # ... (Karşılaştırma Tablosu, Grafik ve PDF indirme kısmı aynı kalır.)
