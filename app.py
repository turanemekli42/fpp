import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import locale
import matplotlib.pyplot as plt # EKLENDİ (Grafikler için)

# PDF OLUŞTURMA İÇİN GEREKLİ KÜTÜPHANE
from fpdf import FPDF 
import base64
import io

# Türkçe yerel ayarlarını ayarla (Çoğu bulut ortamında hata vermemesi için güvenilir formatlamaya geçiyoruz)
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Turkish_Turkey')
    except locale.Error:
        pass


# ======================================================================
# 0. STREAMLIT AYARLARI VE OTURUM DURUMU
# ======================================================================

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
    st.markdown("⚠️ **Dikkat:** Borçlara ve gelirlere özel kurallar, borç ve gelir eklerken tanımlanır. Burası sadece genel simülasyon ayarlarını içerir.")

    st.subheader("Borç Kapatma Stratejisi Çarpanları (Agresiflik)")
    st.markdown("Borçlara Saldırı Gücü (Ek Ödeme) = Kalan Nakit * Çarpan")
    
    COL_A, COL_B, COL_C = st.columns(3)
    with COL_A:
        CARPAN_YUMUSAK = st.number_input("Yumuşak Çarpanı (Konforlu)", value=0.2, min_value=0.0, max_value=1.0, step=0.05, key='carpan_konforlu')
    with COL_B:
        CARPAN_DENGELI = st.number_input("Dengeli Çarpanı (Normal Hız)", value=0.5, min_value=0.0, max_value=1.0, step=0.05, key='carpan_dengeli')
    with COL_C:
        CARPAN_SALDIRGAN = st.number_input("Saldırgan Çarpanı (Maksimum Hız)", value=1.0, min_value=0.0, max_value=1.0, step=0.05, key='carpan_agresif')
        
    STRATEJILER = {
        "Yumuşak (Düşük Ek Ödeme)": CARPAN_YUMUSAK,
        "Dengeli (Orta Ek Ödeme)": CARPAN_DENGELI,
        "Saldırgan (Maksimum Ek Ödeme)": CARPAN_SALDIRGAN
    }
    
    st.markdown("---")
    st.subheader("Faiz Oranı Sapma Senaryoları (Faizli Borçlar İçin Geçerli)")
    st.markdown("Varsayılan borç faiz oranlarını değiştiren genel çarpan.")
    
    col_F1, col_F2, col_F3 = st.columns(3)
    with col_F1:
        FAIZ_CARPAN_IYIMSER = st.number_input("İyimser Senaryo Çarpanı", value=0.8, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_iyimser', 
                                              help="Varsayılan faiz oranlarının %80'i (0.8) ile hesaplanır.")
    with col_F2:
        FAIZ_CARPAN_NORMAL = st.number_input("Normal Senaryo Çarpanı", value=1.0, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_normal',
                                             help="Varsayılan faiz oranları (1.0) ile hesaplanır.")
    with col_F3:
        FAIZ_CARPAN_KOTUMSER = st.number_input("Kötümser Senaryo Çarpanı", value=1.2, min_value=0.0, max_value=2.0, step=0.1, key='faiz_carpan_kotumser',
                                               help="Varsayılan faiz oranlarının %120'si (1.2) ile hesaplanır.")
                                               
    FAIZ_STRATEJILERI = {
        "İyimser Faiz (x0.8)": FAIZ_CARPAN_IYIMSER,
        "Normal Faiz (x1.0)": FAIZ_CARPAN_NORMAL,
        "Kötümser Faiz (x1.2)": FAIZ_CARPAN_KOTUMSER
    }


# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1)
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
                               help="Borç Kapatma öncelikliyse, birikim hedefi borç bitimine kadar esnek tutulur. Birikim öncelikliyse, hedefe ulaşmak için borç kapatma yavaşlayabilir.")

    with col_h2:
        BIRIKIM_TIPI = st.radio("Birikim Hedefi Tipi", 
                                ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"],
                                index=0)
        
        AYLIK_ZORUNLU_BIRIKIM = 0.0
        TOPLAM_BIRIKIM_HEDEFI = 0.0

        if BIRIKIM_TIPI == "Aylık Sabit Tutar":
            AYLIK_ZORUNLU_BIRIKIM = st.number_input("Aylık Zorunlu Birikim Tutarı", 
                                                     value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik',
                                                     help="Borç varken dahi her ay kenara ayırmak istediğiniz minimum tutar.")
        
        else:
            TOPLAM_BIRIKIM_HEDEFI = st.number_input("Hedef Toplam Birikim Tutarı", 
                                                     value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam',
                                                     help="Borçlarınızın bittiği ay elinizde olmasını istediğiniz toplam birikim tutarı.")
        
        if ONCELIK == "Borç Kapatma Hızını Maksimize Et":
            st.success("Borç Kapatma öncelikli: Kalan nakit borca yönlendirilir.")
        else:
            st.info("Birikim Hedefi öncelikli: Aylık nakit akışı önce birikime ayrılır.")

    
    # ======================================================================
    # 1.2. DİNAMİK GELİR EKLEME ARAYÜZÜ
    # ======================================================================
    st.markdown("---")
    st.subheader("Gelir Kaynaklarını Yönet")
    
    # Yardımcı Fonksiyon: Gelir Ekle
    def add_income(isim, tutar, tip, zam_yuzdesi, zam_ayi_gun):
        if tip in ["Ana Maaş", "Yan Gelir (Düzenli)", "Sabit Kira Geliri"]:
            periyot = "Aylık"
            artış_kuralı = "Yıllık Zam"
            artış_oranı = 1 + (zam_yuzdesi / 100.0)
        elif tip == "Yıllık İkramiye/Geri Ödeme":
            periyot = "Tek Seferlik"
            artış_kuralı = "-"
            artış_oranı = 1.0
            zam_yuzdesi = 0
        else: 
            periyot = "Aylık"
            artış_kuralı = "Sabit"
            artış_oranı = 1.0
            zam_yuzdesi = 0 
            
        new_income = {
            "isim": isim,
            "baslangic_tutar": tutar,
            "tip": tip,
            "periyot": periyot,
            "artış_kuralı": artış_kuralı,
            "artış_oranı": artış_oranı,
            "zam_ayi_gun": zam_ayi_gun, 
            "zam_yuzdesi": zam_yuzdesi
        }
        st.session_state.gelirler.append(new_income)
        st.success(f"'{isim}' geliri başarıyla eklendi (Tip: {tip})")


    # Gelir Ekleme Formu
    with st.form("new_income_form", clear_on_submit=True):
        st.markdown("#### Yeni Gelir Ekle")
        
        col_g1, col_g2 = st.columns(2) 
        with col_g1:
            income_name = st.text_input("Gelir Kaynağı Adı", value="Ana Maaş")
            income_type = st.selectbox("Gelir Tipi", 
                                       ["Ana Maaş", "Sabit Kira Geliri", "Yan Gelir (Düzenli)", "Yıllık İkramiye/Geri Ödeme", "Diğer (Sabit)"])
            
        with col_g2:
            initial_tutar = st.number_input("Başlangıç Net Tutarı (TL)", min_value=1.0, value=80000.0)
            
            zam_yuzdesi = 0.0
            zam_ayi = ""
            
            if income_type in ["Ana Maaş", "Sabit Kira Geliri", "Yan Gelir (Düzenli)"]:
                zam_yuzdesi = st.number_input("Yıllık Artış Yüzdesi (Örn: 30)", value=30.0, min_value=0.0, key='income_zam_yuzdesi')
                zam_ayi = st.selectbox("Yıllık Artış Ayı", options=["Ocak", "Temmuz", "Haziran"], index=0, key='income_zam_ayi')
            
            if income_type == "Yıllık İkramiye/Geri Ödeme":
                 zam_ayi = st.selectbox("Gelirin Geleceği Ay", options=aylar_tr, index=9, key='income_tek_seferlik_ayi')
                 st.info("Bu gelir, sadece Simülasyonun başladığı yıl, seçtiğiniz ayda tek seferlik olarak hesaplanır.")


        submit_income_button = st.form_submit_button(label="Geliri Ekle")
        if submit_income_button:
            add_income(income_name, initial_tutar, income_type, zam_yuzdesi, zam_ayi)


    # Eklenen Gelirleri Göster
    if st.session_state.gelirler:
        st.markdown("#### Eklenen Gelir Kaynaklarınız")
        income_data = []
        for i, income in enumerate(st.session_state.gelirler):
            
             if income['tip'] == "Yıllık İkramiye/Geri Ödeme":
                 artış_kuralı_str = f"Tek Seferlik ({income['zam_ayi_gun']} ayında)"
             elif income['tip'] in ["Ana Maaş", "Sabit Kira Geliri", "Yan Gelir (Düzenli)"]:
                 artış_kuralı_str = f"Yıllık %{income['zam_yuzdesi']:.0f} (her {income['zam_ayi_gun']})"
             else:
                 artış_kuralı_str = "Sabit"
                 
             income_data.append({
                 "Gelir Adı": income['isim'],
                 "Tip": income['tip'],
                 "Başlangıç Tutarı": f"₺{income['baslangic_tutar']:,.0f}",
                 "Artış Kuralı": artış_kuralı_str,
             })
        income_df = pd.DataFrame(income_data)
        st.dataframe(income_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        income_to_delete = st.selectbox("Silinecek Gelir Kaynağını Seçin", options=[d['isim'] for d in st.session_state.gelirler] + ["Yok"], index=len(st.session_state.gelirler), key="delete_income_select")
        
        if st.button(f"'{income_to_delete}' Gelirini Sil", key="delete_income_button"):
            if income_to_delete != "Yok":
                st.session_state.gelirler = [d for d in st.session_state.gelirler if d['isim'] != income_to_delete]
                st.warning(f"'{income_to_delete}' geliri silindi. Tekrar hesaplayın.")
                st.rerun()


    # ======================================================================
    # 1.3. BORÇLAR VE SABİT GİDERLER (YÜKÜMLÜLÜKLER)
    # ======================================================================
    st.markdown("---")
    st.subheader("Aylık Yükümlülükler ve Borçlar (Giderler)")
    
    def add_debt(isim, tutar, oncelik, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi):
        
        if borc_tipi == "Kredi Kartı":
            min_kural = "ASGARI_FAIZ" 
        elif borc_tipi == "Ek Hesap":
            min_kural = "FAIZ" 
        elif borc_tipi in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]:
            min_kural = "SABIT_GIDER"
            oncelik = max(1, oncelik) 
            tutar = 0
            faiz_aylik = 0
            kk_asgari_yuzdesi = 0
            sabit_taksit = sabit_taksit or 0 
            kalan_ay = 99999 
            
        elif borc_tipi == "Okul/Eğitim Taksidi":
            min_kural = "SABIT_TAKSIT_GIDER"
            oncelik = max(100, oncelik)
            tutar = 0
            faiz_aylik = 0
            kk_asgari_yuzdesi = 0
            
        elif borc_tipi == "Kredi (Sabit Taksit)":
            min_kural = "SABIT_TAKSIT_ANAPARA" 
            oncelik = max(10, oncelik)
            faiz_aylik = 0
            kk_asgari_yuzdesi = 0
            
        elif borc_tipi == "Diğer (Yüksek Asgari Ödeme)":
            min_kural = "ASGARI_44K" 
        else:
            min_kural = "FAIZ"
        
        ek_bilgiler = {}
        if min_kural.startswith("SABIT"):
             ek_bilgiler = {"sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay}
             final_tutar = tutar if min_kural == "SABIT_TAKSIT_ANAPARA" else 0
        else:
             ek_bilgiler = {"kalan_ay": 1}
             final_tutar = tutar
        
        new_debt = {
            "isim": isim,
            "tutar": final_tutar,
            "min_kural": min_kural,
            "oncelik": oncelik,
            "faiz_aylik": faiz_aylik,
            "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
            **ek_bilgiler
        }
        st.session_state.borclar.append(new_debt)
        st.success(f"'{isim}' yükümlülüğü başarıyla eklendi.")

    with st.form("new_debt_form", clear_on_submit=True):
        st.markdown("#### Yeni Yükümlülük/Borç Ekle")
        
        col_f1, col_f2, col_f3 = st.columns(3) 
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Yükümlülük")
            debt_type = st.selectbox("Yükümlülük Tipi", 
                                     ["Kredi Kartı", "Ek Hesap", 
                                      "--- Sabit Giderler ---", 
                                      "Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti",
                                      "--- Sabit Ödemeli Borçlar ---",
                                      "Kredi (Sabit Taksit)", "Okul/Eğitim Taksidi", 
                                      "--- Diğer Faizli Borçlar ---",
                                      "Diğer (Yüksek Asgari Ödeme)", "Kendi Adın (Faizli)"])
            debt_priority = st.number_input("Öncelik Değeri (1 En Yüksek, 100 En Düşük - Sadece Faizli Borçlar İçin Önemli)", min_value=1, value=5)
            
        with col_f2:
            is_faizli_borc = debt_type in ["Kredi Kartı", "Ek Hesap", "Diğer (Yüksek Asgari Ödeme)", "Kendi Adın (Faizli)"]
            is_sabit_borc = debt_type in ["Kredi (Sabit Taksit)", "Okul/Eğitim Taksidi"]
            is_sabit_gider = debt_type in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]
            
            initial_tutar = 0.0
            debt_taksit = 0.0
            debt_kalan_ay = 1
            
            if is_faizli_borc or debt_type == "Kredi (Sabit Taksit)":
                initial_tutar = st.number_input("Kalan Borç Anaparası", min_value=0.0, value=50000.0, key='initial_tutar')

            if is_sabit_gider:
                debt_taksit = st.number_input("Aylık Zorunlu Gider Tutarı", min_value=1.0, value=5000.0, key='sabit_gider_taksit')
                
            if is_sabit_borc:
                debt_taksit = st.number_input("Aylık Sabit Taksit Tutarı", min_value=1.0, value=5000.0, key='sabit_borc_taksit')
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=12, key='kalan_taksit_ay')
                
        with col_f3:
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0
            
            if is_faizli_borc:
                debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0, key='debt_faiz_aylik') / 100.0
                if debt_type == "Kredi Kartı":
                    debt_kk_asgari_yuzdesi = st.number_input("Asgari Ödeme Anapara Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0, key='kk_asgari') / 100.0
                
        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        if submit_button:
            add_debt(debt_name, initial_tutar, debt_priority, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi)

    if st.session_state.borclar:
        st.markdown("#### Eklenen Yükümlülükleriniz (Önceliğe Göre Sıralı)")
        
        sorted_debts = sorted(st.session_state.borclar, key=lambda x: x['oncelik'])
        
        debt_data = []
        for i, debt in enumerate(sorted_debts):
            
             is_gider = debt['min_kural'] in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
             tutar_gosterim = "Gider Kalemi" if is_gider and debt['tutar'] == 0 else (f"₺{debt['tutar']:,.0f} Kalan" if debt['tutar'] > 0 else "Bitti/Gider")
             
             if debt['min_kural'].startswith("SABIT"):
                 ay_bilgi = f"{debt.get('kalan_ay', 0)} ay" if debt.get('kalan_ay', 0) < 99999 else "Sürekli"
                 ek_bilgi = f"Taksit/Gider: ₺{debt.get('sabit_taksit', 0):,.0f} ({ay_bilgi})"
             else:
                 ek_bilgi = f"Faiz: %{(debt['faiz_aylik'] * 100):.2f}"

             debt_data.append({
                 "Yükümlülük Adı": debt['isim'],
                 "Tip": debt['min_kural'].replace("SABIT_GIDER", "Sabit Gider").replace("SABIT_TAKSIT_GIDER", "Taksitli Gider").replace("SABIT_TAKSIT_ANAPARA", "Sabit Kredi"),
                 "Öncelik": debt['oncelik'],
                 "Kalan/Ödeme Tutarı": tutar_gosterim,
                 "Ek Bilgi": ek_bilgi
             })
        
        debt_df = pd.DataFrame(debt_data)
        st.dataframe(debt_df, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        debt_to_delete = st.selectbox("Silinecek Yükümlülüğü Seçin", options=[d['isim'] for d in sorted_debts] + ["Yok"], index=len(sorted_debts), key="delete_debt_select")
        
        if st.button(f"'{debt_to_delete}' Yükümlülüğünü Sil", key="delete_debt_button"):
            if debt_to_delete != "Yok":
                st.session_state.borclar = [d for d in st.session_state.borclar if d['isim'] != debt_to_delete]
                st.warning(f"'{debt_to_delete}' yükümlülüğü silindi. Tekrar hesaplayın.")
                st.rerun()


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
    if value is None:
        value = 0
    # Manuel formatlamaya geç: Örnek: 1234567.89 -> ₺1.234.568
    tam_sayi = int(round(value))
    
    # Binler basamağı için nokta (.) kullanmak için karmaşık f-string manipülasyonu
    formatted_value = f"₺{tam_sayi:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted_value

def hesapla_min_odeme(borc, faiz_carpani=1.0): # PARAMETRE EKLENDİ
    """Her bir borç için minimum ödeme tutarını o borca ait kurala göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    faiz_aylik = borc['faiz_aylik'] * faiz_carpani # ÇARPAN KULLANILDI
    kk_asgari_yuzdesi = borc['kk_asgari_yuzdesi']
    
    ASGARI_44K_DEGERI = 45000 
    
    if tutar <= 0 and not kural.startswith("SABIT"): return 0
    
    if kural == "SABIT_GIDER":
          return borc.get('sabit_taksit', 0)
          
    if kural in ["SABIT_TAKSIT_GIDER", "SABIT_TAKSIT_ANAPARA"]:
        if borc.get('kalan_ay', 0) > 0:
            return borc.get('sabit_taksit', 0)
        return 0
    
    if kural == "FAIZ":
        return tutar * faiz_aylik # Yeni faiz oranını kullan
    
    elif kural == "ASGARI_44K":
        return min(tutar, ASGARI_44K_DEGERI) 
        
    elif kural == "ASGARI_FAIZ":
        # Min ödeme = (Faiz) + (Anaparanın Asgari Yüzdesi)
        return (tutar * faiz_aylik) + (tutar * kk_asgari_yuzdesi) # Yeni faiz oranını kullan
        
    return 0
    
# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU - GÜNCELLENDİ
# ----------------------------------------------------------------------

def simule_borc_planı(borclar_listesi, gelirler_listesi, agresiflik_carpani, faiz_carpani, hedef_tipi, aylik_min_birikim, toplam_birikim_hedefi, oncelik): # PARAMETRE EKLENDİ
    
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
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])
    
    ilk_ay_toplam_gelir = 0
    mevcut_birikim = 0.0 

    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Dinamik Gelir Hesaplama
        toplam_gelir = 0
        
        for gelir in mevcut_gelirler:
            gelir_tutari = gelir['baslangic_tutar']
            
            if gelir['tip'] == "Yıllık İkramiye/Geri Ödeme":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                
                gelir_id = (gelir['isim'], gelir['tip'])
                
                # Sadece simülasyon başlangıç yılı içinde ve yalnızca bir kez ekle
                if (tarih.month == zam_ay_no and 
                    tarih.year >= sim_baslangic_tarihi.year and 
                    gelir_id not in st.session_state.tek_seferlik_gelir_isaretleyicisi):
                    
                    toplam_gelir += gelir_tutari
                    st.session_state.tek_seferlik_gelir_isaretleyicisi.add(gelir_id)
                    
            elif gelir['artış_kuralı'] == "Yıllık Zam":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                if tarih.month == zam_ay_no and tarih > sim_baslangic_tarihi:
                    artış_oranı = 1 + (gelir['zam_yuzdesi'] / 100.0)
                    gelir['baslangic_tutar'] = gelir_tutari * artış_oranı
                    gelir_tutari = gelir['baslangic_tutar']
                toplam_gelir += gelir_tutari
            else:
                toplam_gelir += gelir_tutari
        
        if ay_sayisi == 0:
            ilk_ay_toplam_gelir = toplam_gelir
        
        
        # 3.2. Yükümlülük Ödemeleri (Giderler + Min. Borç Ödemeleri)
        zorunlu_gider_toplam = 0
        min_borc_odeme_toplam = 0
        
        for borc in mevcut_borclar:
            min_odeme = hesapla_min_odeme(borc, faiz_carpani) # ÇARPAN GÖNDERİLDİ
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
        
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])
        
        birikime_ayrilan = 0.0
        saldırı_gucu = 0.0
        
        if yuksek_oncelikli_borclar_kaldi:
            
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
        
        mevcut_birikim += birikime_ayrilan
            
        # 3.5. Borçlara Ödeme Uygulama
        
        saldırı_kalan = saldırı_gucu
        kapanan_borclar_listesi = []
        
        # a) Taksit/Faiz/Min Ödeme İşlemleri
        for borc in mevcut_borclar:
            
            if borc['min_kural'].startswith("SABIT"):
                if borc['min_kural'] in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                    borc['kalan_ay'] = max(0, borc['kalan_ay'] - 1)
                    if borc['min_kural'] == 'SABIT_TAKSIT_ANAPARA':
                         borc['tutar'] -= borc.get('sabit_taksit', 0)
            else: 
                if borc['tutar'] > 0:
                    etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani # ÇARPAN KULLANILDI
                    eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani 
                    toplam_faiz_maliyeti += eklenen_faiz
                    
                    min_odeme = hesapla_min_odeme(borc, faiz_carpani) # ÇARPAN GÖNDERİLDİ
                    borc['tutar'] += eklenen_faiz 
                    borc['tutar'] -= min_odeme 
                    
        # b) Saldırı Gücünü Uygulama (Faiz Çığı Mantığı)
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 1 and saldırı_kalan > 0 and borc['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0

        # 3.6. Sonuçları Kaydetme ve Döngü Kontrolü
        
        kalan_faizli_borc_toplam = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])
        
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
# 4. YORUM VE GRAFİK FONKSİYONLARI - EKLENDİ/GÜNCELLENDİ
# ----------------------------------------------------------------------

def yap_finansal_yorum(oran, birikim_hedefi_str):
    """Gelir/Gider oranına göre dinamik yorum yapar."""
    
    if oran >= 1.05:
        return ("🔴 KRİTİK DURUM: Finansal Boğulma Riski!", 
                "Aylık zorunlu giderleriniz (min. borç ödemeleri dahil) gelirinizin üzerindedir. Bu durum acil nakit akışı sorununa yol açacaktır. Gelirleri artırmak veya zorunlu yükümlülükleri acilen kısmak zorundasınız. Bu senaryoda ek borç ödemesi ve birikim imkansızdır.")
    
    elif oran >= 0.95:
        return ("🟠 YÜKSEK RİSK: Başabaş Noktası!", 
                f"Aylık gelirinizin %{oran*100:,.0f}'ü zorunlu yükümlülüklere gitmektedir. Çok dar bir marjınız var. En ufak bir ek harcama veya aksilik sizi negatif nakit akışına itebilir. '{birikim_hedefi_str}' gibi bir birikim hedefi çok zorlu olacaktır. Ek ödeme gücünüz çok düşüktür.")
                
    elif oran >= 0.70:
        return ("🟡 ZORLU DENGE: Ağır Yükümlülükler!", 
                f"Gelirinizin %{oran*100:,.0f}'ü temel ve zorunlu ödemelere ayrılıyor. Borç kapatma süreci uzun ve yorucu olacaktır. Borç bitene kadar harcamalarınızı ciddi şekilde kontrol etmeli ve Yıllık İkramiyeleri tamamen borç kapatmaya yönlendirmelisiniz.")
        
    elif oran >= 0.50:
        return ("🟢 YÖNETİLEBİLİR YÜK: Dengeli Durum", 
                f"Gelirinizin %{oran*100:,.0f}'si zorunlu yükümlülüklere gidiyor. Borç yükünüz yönetilebilir seviyededir. Dengeli stratejiyi seçerek hem borçlarınızı hem de birikiminizi ilerletebilirsiniz.")
        
    else:
        return ("🔵 KONFORLU FİNANS: Güçlü Durum", 
                f"Gelirinizin sadece %{oran*100:,.0f}'i zorunlu ödemelere gidiyor. Çok güçlü bir nakit akışınız var. Saldırgan stratejiyi seçerek faiz maliyetinizi minimuma indirin veya Birikim Hedefini yükseltmeyi düşünebilirsiniz.")

def create_comparison_chart(all_scenarios):
    """Tüm senaryoların kalan borç toplamını karşılaştıran bir çizgi grafik oluşturur."""
    
    # Streamlit Cloud/Linux ortamında Türkçe font uyumu için ayar
    plt.rcParams.update({'font.family': 'DejaVu Sans'}) 
    
    fig, ax = plt.subplots(figsize=(10, 6))
    max_months = 0
    
    for strategy_name, result in all_scenarios.items():
        df = result['df']
        months = np.arange(1, len(df) + 1)
        kalan_borc = df['Kalan Faizli Borç Toplamı'].tolist()
        
        # Grafik eksenini düzgün kapatmak için (Borç bittiyse son noktayı sıfır olarak ekle)
        if kalan_borc and kalan_borc[-1] > 0 and len(kalan_borc) < 60: 
            kalan_borc.append(0)
            months = np.append(months, months[-1] + 1)
        
        ax.plot(months, kalan_borc, label=strategy_name)
        max_months = max(max_months, len(df))

    # Grafik Ayarları
    ax.set_title("Stratejilere Göre Kalan Faizli Borç Gelişimi", fontsize=14)
    ax.set_xlabel("Ay Sayısı", fontsize=12)
    ax.set_ylabel("Kalan Borç Tutarı (TL)", fontsize=12)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(title="Senaryo", loc='upper right', fontsize=8)
    
    # X eksenini borcun bittiği son aya göre sınırla
    ax.set_xlim(0, max_months + 2) 

    # Y ekseninde (TL) formatlama
    from matplotlib.ticker import FuncFormatter
    formatter = FuncFormatter(lambda x, pos: f'₺{int(x/1000):,}K' if x >= 1000 else f'₺{int(x):,}')
    ax.yaxis.set_major_formatter(formatter)

    return fig

# ----------------------------------------------------------------------
# 5. PDF OLUŞTURMA FONKSİYONU
# ----------------------------------------------------------------------

class PDF(FPDF):
    """Türkçe karakter destekli basit PDF sınıfı"""
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Finansal Borç Yönetimi Simülasyon Raporu', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Sayfa {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 8, title, 0, 1, 'L')
        self.ln(2)

    def chapter_body(self, body, is_code=False):
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, body)
        self.ln(5)
        
    def print_dataframe(self, df):
        # Sütun isimlerini yazdır
        self.set_font('Arial', 'B', 8)
        col_widths = [20, 10, 20, 25, 25, 25, 20, 25] # Sabit genişlikler
        col_headers = [
            "Ay", "Süre", "Gelir", "Min. Odeme", "Saldiri Gucu", 
            "Birikim", "Kapanan Borc", "Kalan Borc"
        ]

        # Header
        for header, width in zip(col_headers, col_widths):
             self.cell(width, 7, header, 1, 0, 'C')
        self.ln()

        # Data
        self.set_font('Arial', '', 7)
        for index, row in df.iterrows():
            if index % 40 == 0 and index != 0: # Sayfa sonu kontrolü
                self.add_page()
                self.set_font('Arial', 'B', 8)
                for header, width in zip(col_headers, col_widths):
                    self.cell(width, 7, header, 1, 0, 'C')
                self.ln()
                self.set_font('Arial', '', 7)

            self.cell(col_widths[0], 6, row['Ay'], 1, 0, 'C')
            self.cell(col_widths[1], 6, str(index + 1), 1, 0, 'C') # Ay Sayısı
            self.cell(col_widths[2], 6, format_tl(row['Toplam Gelir']), 1, 0, 'R')
            self.cell(col_widths[3], 6, format_tl(row['Min. Borç Ödemeleri']), 1, 0, 'R')
            self.cell(col_widths[4], 6, format_tl(row['Borç Saldırı Gücü']), 1, 0, 'R')
            self.cell(col_widths[5], 6, format_tl(row['Aylık Birikim Katkısı']), 1, 0, 'R')
            self.cell(col_widths[6], 6, row['Kapanan Borç'] if row['Kapanan Borç'] != '-' else 'Yok', 1, 0, 'L')
            self.cell(col_widths[7], 6, format_tl(row['Kalan Faizli Borç Toplamı']), 1, 0, 'R')
            self.ln()
        self.ln(5)

def create_pdf(results_dict, strategy_name, genel_yorum_baslik, genel_yorum_metin):
    """
    Simülasyon sonuçlarını alıp bir PDF raporu oluşturur ve bayt olarak döndürür.
    """
    
    pdf = PDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # --- 1. Genel Yorum ve Özet ---
    pdf.chapter_title(f"1. Simülasyon Özeti - Senaryo: {strategy_name}")
    pdf.chapter_body(f"Başlangıç Tarihi: {SIM_BASLANGIC_AYI}")
    pdf.chapter_body(f"Faizli Borç Yükü: {format_tl(results_dict['baslangic_faizli_borc'])}")
    pdf.chapter_body(f"Toplam Borç Kapatma Süresi: {results_dict['ay_sayisi']} Ay")
    pdf.chapter_body(f"Toplam Faiz Maliyeti: {format_tl(results_dict['toplam_faiz'])}")
    pdf.chapter_body(f"Simülasyon Sonu Toplam Birikim: {format_tl(results_dict['toplam_birikim'])}")
    pdf.ln(5)

    # --- 2. Finansal Yorum ---
    pdf.chapter_title(f"2. Finansal Durum Yorumu: {genel_yorum_baslik}")
    pdf.chapter_body(genel_yorum_metin)
    pdf.ln(5)
    
    # --- 3. Aylık Detaylar ---
    pdf.chapter_title("3. Aylık Nakit Akışı Detay Tablosu")
    
    # DataFrame'i yeniden düzenle (sadece gerekli sütunlar ve formatlama)
    df = results_dict['df'].copy()
    
    df = df[['Ay', 'Toplam Gelir', 'Min. Borç Ödemeleri', 'Borç Saldırı Gücü', 'Aylık Birikim Katkısı', 'Kapanan Borç', 'Kalan Faizli Borç Toplamı']]
    
    pdf.print_dataframe(df)
    
    # PDF'i bayt olarak döndür
    pdf_output = pdf.output(dest='S').encode('latin1')
    
    return pdf_output

# ----------------------------------------------------------------------
# 6. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ - GÜNCELLENDİ
# ----------------------------------------------------------------------

if calculate_button:
    
    # --- HATA KONTROLÜ ---
    if not st.session_state.gelirler:
        st.error("Lütfen simülasyonu başlatmak için en az bir **Gelir Kaynağı** ekleyin.")
        st.stop()
        
    if not st.session_state.borclar:
        st.error("Lütfen simülasyonu başlatmak için en az bir **Yükümlülük/Borç** ekleyin.")
        st.stop()
        
    # 'tek_seferlik_gelir_isaretleyicisi' setini sıfırla
    st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

    # Başlangıç Yorumu İçin Temel Oranı Hesapla (Normal Faiz/Agresiflik çarpanı)
    temp_result = simule_borc_planı(
        st.session_state.borclar, 
        st.session_state.gelirler, 
        0.0, # Agresiflik 0 (Sadece zorunlu ödemeyi baz alır)
        1.0, # Normal Faiz Çarpanı (1.0)
        BIRIKIM_TIPI, 
        AYLIK_ZORUNLU_BIRIKIM, 
        TOPLAM_BIRIKIM_HEDEFI, 
        ONCELIK
    )
    
    # Gerekli Temel Veriler
    oran = temp_result['ilk_ay_gider'] / temp_result['ilk_ay_gelir'] if temp_result['ilk_ay_gelir'] > 0 else 999.0
    birikim_hedefi_str = "Aylık Birikim" if BIRIKIM_TIPI == "Aylık Sabit Tutar" else "Toplam Birikim"
    genel_yorum_baslik, genel_yorum_metin = yap_finansal_yorum(oran, birikim_hedefi_str)

    st.markdown("---")
    st.header("Genel Finansal Durum Değerlendirmesi")
    st.metric(label="Zorunlu Gider/Gelir Oranı (İlk Ay)", value=f"%{oran*100:,.1f}")
    
    # Yorumu renklendir
    if "KRİTİK" in genel_yorum_baslik:
        st.error(f"**{genel_yorum_baslik}**\n\n{genel_yorum_metin}")
    elif "YÜKSEK RİSK" in genel_yorum_baslik:
        st.warning(f"**{genel_yorum_baslik}**\n\n{genel_yorum_metin}")
    else:
        st.success(f"**{genel_yorum_baslik}**\n\n{genel_yorum_metin}")
    
    # --- TÜM SENARYOLARI SİMULE ET (Faiz & Agresiflik) ---
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
                ONCELIK
            )
            # Her senaryo arası tek seferlik gelir işaretleyicisini sıfırla
            st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

    st.markdown("---")
    st.header("Tüm Senaryoların Karşılaştırması (Faiz & Agresiflik)")
    
    # Karşılaştırma tablosu oluştur
    karsilastirma_data = []
    for name, res in all_scenarios.items():
        karsilastirma_data.append({
            "Senaryo": name,
            "Borç Bitiş Süresi": f"{res['ay_sayisi']} Ay",
            "Toplam Faiz Maliyeti": format_tl(res['toplam_faiz']),
            "Toplam Birikim": format_tl(res['toplam_birikim']),
            "Tasarruf Oranı": f"%{100 - (res['toplam_faiz'] * 100 / res['baslangic_faizli_borc']):,.1f}" if res['baslangic_faizli_borc'] > 0 else "N/A"
        })
    
    karsilastirma_df = pd.DataFrame(karsilastirma_data)
    st.dataframe(karsilastirma_df, use_container_width=True, hide_index=True)

    # --- GRAFİKSEL GÖSTERİM ---
    st.subheader("Borç Kapatma Hız Grafiği")
    fig = create_comparison_chart(all_scenarios)
    st.pyplot(fig) # Streamlit ile grafiği göster
    
    # Detay ve PDF İndirme Kısmı
    st.markdown("---")
    st.subheader("Seçilen Senaryonun Detayları ve PDF Raporu")
    
    secilen_senaryo = st.selectbox("Detaylarını Görmek ve İndirmek İstediğiniz Senaryoyu Seçin", options=list(all_scenarios.keys()), index=4)
    
    secilen_sonuc = all_scenarios[secilen_senaryo]
    st.dataframe(secilen_sonuc['df'], use_container_width=True, hide_index=True)
    
    # PDF Oluşturma ve İndirme Butonu
    pdf_bytes = create_pdf(secilen_sonuc, secilen_senaryo, genel_yorum_baslik, genel_yorum_metin)
    
    st.download_button(
        label=f"'{secilen_senaryo}' Raporunu PDF Olarak İndir",
        data=pdf_bytes,
        file_name=f"Finansal_Rapor_{secilen_senaryo.replace(' / ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/octet-stream"
    )
