import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np
import locale

# Türkçe yerel ayarlarını ayarla (para birimi ve tarih formatı için)
# Sisteminize göre farklılık gösterebilir. 'tr_TR.UTF-8' çoğu Linux/macOS'ta çalışır.
# Windows için 'Turkish_Turkey' kullanabilirsiniz.
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Turkish_Turkey')
    except locale.Error:
        pass # Eğer hiçbiri çalışmazsa varsayılanı kullanır.


# ======================================================================
# 0. STREAMLIT OTURUM DURUMUNU BAŞLATMA
# ======================================================================

if 'borclar' not in st.session_state:
    st.session_state.borclar = []
if 'gelirler' not in st.session_state:
    st.session_state.gelirler = []

# ======================================================================
# 1. STREAMLIT KULLANICI GİRİŞLERİ (SEKMELER)
# ======================================================================

st.set_page_config(layout="wide")
st.title("Finansal Borç Yönetimi Simülasyon Projesi")
st.markdown("---")
tab1, tab2 = st.tabs(["📊 Simülasyon Verileri", "⚙️ Yönetici Kuralları"])

# --------------------------------------------------
# Yönetici Kuralları Sekmesi (tab2)
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
        
    # Tüm stratejileri bir sözlükte topluyoruz
    STRATEJILER = {
        "Yumuşak (Düşük Ek Ödeme)": CARPAN_YUMUSAK,
        "Dengeli (Orta Ek Ödeme)": CARPAN_DENGELI,
        "Saldırgan (Maksimum Ek Ödeme)": CARPAN_SALDIRGAN
    }


# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1)
# --------------------------------------------------
with tab1:
    
    # ======================================================================
    # 1.1. GENEL HEDEFLER VE DİĞER GİDERLER
    # ======================================================================
    st.header("Simülasyon Hedefleri ve Sabit Giderler")

    aylar_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    
    col_h1, col_h2 = st.columns(2)
    with col_h1:
        SIM_BASLANGIC_AYI = st.selectbox("Simülasyon Başlangıç Ayı", options=[f"{a} {y}" for y in range(2025, 2027) for a in aylar_tr], index=9)
        
        sim_bas_yil = int(SIM_BASLANGIC_AYI.split()[1])
        hedef_ay_str = st.selectbox("Hedef Borç Kapatma Ayı", options=aylar_tr, index=5, key='hedef_ay')
        hedef_yil = st.number_input("Hedef Borç Kapatma Yılı", min_value=sim_bas_yil, max_value=sim_bas_yil + 5, value=sim_bas_yil + 2, key='hedef_yil')
        HEDEF_BITIS_TARIHI = f"{hedef_ay_str} {hedef_yil}"
        
    with col_h2:
        ZORUNLU_SABIT_GIDER = st.number_input("Diğer Sabit Giderler (Kira, Fatura vb.)", value=20000, step=1000, min_value=0, key='zorunlu_gider')
        AYLIK_ZORUNLU_BIRIKIM = st.number_input("Aylık Zorunlu Birikim (Borç varken ayrılması gereken)", value=5000, step=500, min_value=0, key='zorunlu_birikim')
        EV_KREDISI_TAKSIT = st.number_input("Ev Kredisi Taksiti (Borç değil, Sadece Giderse)", value=15000, step=1000, min_value=0, key='ev_kredi_taksit')
        
    # ======================================================================
    # 1.2. DİNAMİK GELİR EKLEME ARAYÜZÜ (Zam Yüzdesi Gelire Özel)
    # ======================================================================
    st.markdown("---")
    st.subheader("Gelir Kaynaklarını Yönet")
    
    # Yardımcı Fonksiyon: Gelir Ekle
    def add_income(isim, tutar, tip, zam_yuzdesi, zam_ayi_gun):
        if tip in ["Maaş", "Sabit Kira Geliri"]:
            periyot = "Aylık"
            artış_kuralı = "Yıllık Zam"
            artış_oranı = 1 + (zam_yuzdesi / 100.0)
        elif tip == "Tek Seferlik Gelir (İkramiye)":
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
                                    ["Maaş", "Sabit Kira Geliri", "Diğer (Sabit)", "Tek Seferlik Gelir (İkramiye)"])
            
        with col_g2:
            initial_tutar = st.number_input("Başlangıç Net Tutarı (TL)", min_value=1.0, value=80000.0)
            
            zam_yuzdesi = 0.0
            zam_ayi = ""
            
            if income_type in ["Maaş", "Sabit Kira Geliri"]:
                # Gelire özel zam yüzdesi
                zam_yuzdesi = st.number_input("Yıllık Zam Yüzdesi (Örn: 30)", value=30.0, min_value=0.0, key='income_zam_yuzdesi')
                zam_ayi = st.selectbox("Yıllık Zam Ayı", options=["Ocak", "Temmuz", "Haziran"], index=0, key='income_zam_ayi')
            
            if income_type == "Tek Seferlik Gelir (İkramiye)":
                 zam_ayi = st.selectbox("Tek Seferlik Gelirin Geldiği Ay", options=aylar_tr, index=9, key='income_tek_seferlik_ayi')


        submit_income_button = st.form_submit_button(label="Geliri Ekle")
        if submit_income_button:
            add_income(income_name, initial_tutar, income_type, zam_yuzdesi, zam_ayi)


    # Eklenen Gelirleri Göster ve Silme Seçeneği Sun (Kısaltıldı)
    if st.session_state.gelirler:
        st.markdown("#### Eklenen Gelir Kaynaklarınız")
        income_data = []
        for i, income in enumerate(st.session_state.gelirler):
             income_data.append({
                 "Gelir Adı": income['isim'],
                 "Tip": income['tip'],
                 "Başlangıç Tutarı": f"₺{income['baslangic_tutar']:,.0f}",
                 "Artış Kuralı": f"{income['zam_yuzdesi']}% her {income['zam_ayi_gun']}" if income['tip'] in ["Maaş", "Sabit Kira Geliri"] else income['periyot'],
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
    # 1.3. BORÇ EKLEME ARAYÜZÜ (Kural ve Faiz Borca Özel)
    # ======================================================================
    st.markdown("---")
    st.subheader("Borçları ve Sabit Taksitli Yükümlülükleri Yönet")
    
    # Yardımcı Fonksiyon: Borç Ekle
    def add_debt(isim, tutar, oncelik, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi):
        
        if borc_tipi == "Kredi Kartı":
            min_kural = "ASGARI_FAIZ" 
        elif borc_tipi == "Ek Hesap":
            min_kural = "FAIZ" 
        elif borc_tipi == "Okul/Eğitim Taksidi":
            min_kural = "SABIT_TAKSIT_GIDER"
            oncelik = max(100, oncelik) # Giderler en sona
            tutar = 0
        elif borc_tipi == "Kredi (Sabit Taksit)":
            min_kural = "SABIT_TAKSIT_ANAPARA" 
            oncelik = max(10, oncelik) # Sabit taksitliler daha sonra kapanır
        elif borc_tipi == "Diğer (Yüksek Asgari Ödeme)":
            min_kural = "ASGARI_44K" 
        else:
            min_kural = "FAIZ"
        
        ek_bilgiler = {}
        if min_kural.startswith("SABIT_TAKSIT"):
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
            "faiz_aylik": faiz_aylik,              # Borca özel faiz
            "kk_asgari_yuzdesi": kk_asgari_yuzdesi, # Borca özel asgari yüzde
            **ek_bilgiler
        }
        st.session_state.borclar.append(new_debt)
        st.success(f"'{isim}' borcu başarıyla eklendi (Faiz: %{faiz_aylik*100:,.2f})")

    # Borç Ekleme Formu
    with st.form("new_debt_form", clear_on_submit=True):
        st.markdown("#### Yeni Yükümlülük Ekle")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Yükümlülük")
            debt_type = st.selectbox("Yükümlülük Tipi", 
                                    ["Kredi Kartı", "Ek Hesap", "Kredi (Sabit Taksit)", "Okul/Eğitim Taksidi", "Diğer (Yüksek Asgari Ödeme)", "Kendi Adın (Faizli)"])
            debt_priority = st.number_input("Öncelik Değeri (1 en yüksek, 100 en düşük)", min_value=1, value=5)
            
        with col_f2:
            initial_tutar = st.number_input("Kalan Borç Anaparası (Faizli borçlar için)", min_value=0.0, value=50000.0)
            
            if debt_type in ["Kredi (Sabit Taksit)", "Okul/Eğitim Taksidi"]:
                debt_taksit = st.number_input("Aylık Sabit Taksit Tutarı", min_value=1.0, value=5000.0)
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=12)
            else:
                debt_taksit = 0.0
                debt_kalan_ay = 1 
                
        with col_f3:
            # Borca özel faiz ve asgari ödeme
            debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=5.0, step=0.05, min_value=0.0) / 100.0
            if debt_type == "Kredi Kartı":
                debt_kk_asgari_yuzdesi = st.number_input("Asgari Ödeme Anapara Yüzdesi (%)", value=5.0, step=1.0, min_value=0.0) / 100.0
            else:
                debt_kk_asgari_yuzdesi = 0.0

        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        if submit_button:
            add_debt(debt_name, initial_tutar, debt_priority, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi)

    # Eklenen Borçları Göster ve Silme Seçeneği Sun (Kısaltıldı)
    if st.session_state.borclar:
        st.markdown("#### Eklenen Yükümlülükleriniz (Önceliğe Göre Sıralı)")
        sorted_debts = sorted(st.session_state.borclar, key=lambda x: x['oncelik'])
        debt_data = []
        for i, debt in enumerate(sorted_debts):
             tutar_gosterim = f"₺{debt['tutar']:,.0f}" if debt['min_kural'] not in ['SABIT_TAKSIT_ANAPARA', 'SABIT_TAKSIT_GIDER'] else (f"₺{debt['tutar']:,.0f} Kalan" if debt['tutar'] > 0 else "Gider Kalemi")
             
             if debt['min_kural'].startswith("SABIT_TAKSIT"):
                 ek_bilgi = f"Taksit: ₺{debt.get('sabit_taksit', 0):,.0f} x {debt.get('kalan_ay', 0)} ay"
             else:
                 ek_bilgi = f"Faiz: %{(debt['faiz_aylik'] * 100):.2f}"

             debt_data.append({
                 "Yükümlülük Adı": debt['isim'],
                 "Öncelik": debt['oncelik'],
                 "Kural": debt['min_kural'].replace("SABIT_TAKSIT_GIDER", "GİDER KALEMİ").replace("SABIT_TAKSIT_ANAPARA", "SABİT KREDİ"),
                 "Kalan Tutar": tutar_gosterim,
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
# 2. YARDIMCI FONKSIYONLAR (Minimum Ödeme Hesaplama Mantığı)
# ----------------------------------------------------------------------

def hesapla_min_odeme(borc):
    """Her bir borç için minimum ödeme tutarını o borca ait kurala göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    faiz_aylik = borc['faiz_aylik']
    kk_asgari_yuzdesi = borc['kk_asgari_yuzdesi']
    
    ASGARI_44K_DEGERI = 45000 
    
    if tutar <= 0 and not kural.endswith("_GIDER"): return 0
    if kural == "SABIT_TAKSIT_GIDER":
        if borc.get('kalan_ay', 0) > 0:
            return borc.get('sabit_taksit', 0)
        return 0

    if kural == "FAIZ":
        return tutar * faiz_aylik
    
    elif kural == "ASGARI_44K":
        return min(tutar, ASGARI_44K_DEGERI) 
        
    elif kural == "ASGARI_FAIZ":
        return (tutar * faiz_aylik) + (tutar * kk_asgari_yuzdesi)
        
    elif kural == "SABIT_TAKSIT_ANAPARA":
        if borc.get('kalan_ay', 0) > 0:
             return borc.get('sabit_taksit', 0)
        return 0
        
    return 0
    
# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU
# ----------------------------------------------------------------------

def simule_borc_planı(borclar_listesi, gelirler_listesi, agresiflik_carpani):
    
    aylik_sonuclar = []
    # Simülasyon sırasında değişecekleri kopyala
    mevcut_borclar = [b.copy() for b in borclar_listesi] 
    mevcut_gelirler = [g.copy() for g in gelirler_listesi] 
    
    # Başlangıç ve yardımcı değişkenler
    ay_str = SIM_BASLANGIC_AYI.split()
    aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
    sim_baslangic_tarihi = datetime(int(ay_str[1]), aylar_map[ay_str[0]], 1)
    tarih = sim_baslangic_tarihi
    
    ay_sayisi = 0
    max_iterasyon = 60 # 5 yıl
    
    toplam_faiz_maliyeti = 0 
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])
    
    # Simülasyonun ilk ayı için toplam gelir ve zorunlu gideri hesaplayacağız (Yorum için gerekli)
    ilk_ay_toplam_gelir = 0
    
    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Dinamik Gelir Hesaplama ve Zam Uygulama
        toplam_gelir = 0
        
        for gelir in mevcut_gelirler:
            gelir_tutari = gelir['baslangic_tutar']
            
            if gelir['tip'] == "Tek Seferlik Gelir (İkramiye)":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                if tarih.month == zam_ay_no and tarih.year == sim_baslangic_tarihi.year:
                    toplam_gelir += gelir_tutari
                    
            elif gelir['artış_kuralı'] == "Yıllık Zam":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                
                if tarih.month == zam_ay_no and tarih > sim_baslangic_tarihi:
                    artış_oranı = 1 + (gelir['zam_yuzdesi'] / 100.0)
                    gelir['baslangic_tutar'] = gelir_tutari * artış_oranı
                    gelir_tutari = gelir['baslangic_tutar']
                        
                toplam_gelir += gelir_tutari

            else:
                toplam_gelir += gelir_tutari
        
        # İlk ayki toplam geliri kaydet
        if ay_sayisi == 0:
            ilk_ay_toplam_gelir = toplam_gelir
        
        
        # Diğer Zorunlu Giderler (Statik)
        zorunlu_gider_toplam = ZORUNLU_SABIT_GIDER + EV_KREDISI_TAKSIT
        
        # Taksitli Giderler (Okul/Eğitim) ve Sabit Taksitli Krediler
        okul_taksidi_gider = 0
        sabit_taksitli_kredi_toplam = 0
        
        for borc in mevcut_borclar:
            if borc['min_kural'] == 'SABIT_TAKSIT_GIDER' and borc.get('kalan_ay', 0) > 0:
                 okul_taksidi_gider += borc.get('sabit_taksit', 0)
                 
            if borc['min_kural'] == 'SABIT_TAKSIT_ANAPARA' and borc.get('kalan_ay', 0) > 0:
                 sabit_taksitli_kredi_toplam += borc.get('sabit_taksit', 0)
                 
        zorunlu_gider_toplam += okul_taksidi_gider
        
        # 3.2. Minimum Borç Ödemeleri Hesaplama
        min_odeme_toplam = 0
        for borc in mevcut_borclar:
            if borc['tutar'] > 0:
                if borc['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                    min_odeme_toplam += hesapla_min_odeme(borc) # Borca özel kuralları kullan
                    
        # İlk ayki Min. Borç Ödeme Toplamını kaydet (Yorum için gerekli)
        if ay_sayisi == 0:
             ilk_ay_min_odeme = min_odeme_toplam

        
        # 3.3. Saldırı Gücü (Attack Power) Hesaplama
        
        giderler_dahil_min_odeme = zorunlu_gider_toplam + sabit_taksitli_kredi_toplam + min_odeme_toplam
        kalan_nakit_brut = toplam_gelir - giderler_dahil_min_odeme
        kalan_nakit = max(0, kalan_nakit_brut) 
        
        # Zorunlu Birikimi düş
        ek_birikim = min(AYLIK_ZORUNLU_BIRIKIM, kalan_nakit)
        kalan_nakit -= ek_birikim 
        
        # Borç Kapatma Saldırı Gücü (Agresiflik Çarpanı ile çarpılır)
        saldırı_gucu = kalan_nakit * agresiflik_carpani
             
        # Borç Kapatma Kontrolü (Faizli Borçlar bittiyse tüm kalan nakit birikime gider)
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])

        birikim = ek_birikim
        if not yuksek_oncelikli_borclar_kaldi and kalan_nakit > 0:
             birikim += kalan_nakit
             saldırı_gucu = 0
             
        # 3.4. Borçlara Ödeme Uygulama
        
        saldırı_kalan = saldırı_gucu
        kapanan_borclar_listesi = []
        
        # a) Taksit/Faiz/Min Ödeme İşlemleri
        for borc in mevcut_borclar:
            if borc['tutar'] > 0 or borc['min_kural'] == 'SABIT_TAKSIT_GIDER':
                
                if borc['min_kural'].startswith("SABIT_TAKSIT"):
                    borc['kalan_ay'] = max(0, borc['kalan_ay'] - 1)
                    if borc['min_kural'] == 'SABIT_TAKSIT_ANAPARA':
                         borc['tutar'] -= borc.get('sabit_taksit', 0)
                else: 
                    # Faizli Borçlar
                    eklenen_faiz = borc['tutar'] * borc['faiz_aylik'] # Borca özel faiz
                    toplam_faiz_maliyeti += eklenen_faiz
                    
                    min_odeme = hesapla_min_odeme(borc) # Borca özel kural
                    borc['tutar'] += eklenen_faiz 
                    borc['tutar'] -= min_odeme 
                    
        # b) Saldırı Gücünü Uygulama (Faiz Çığı Mantığı)
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 1 and saldırı_kalan > 0 and borc['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA']:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0

        # 3.5. Sonuçları Kaydetme ve Döngü Kontrolü
        
        kalan_faizli_borc_toplam = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])
        
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir),
            'Toplam Sabit Giderler': round(zorunlu_gider_toplam + sabit_taksitli_kredi_toplam),
            'Min. Borç Ödemeleri (Faiz Çığının Serbest Bıraktığı)': round(min_odeme_toplam),
            'Borç Saldırı Gücü (Ek Ödeme)': round(saldırı_gucu - saldırı_kalan),
            'Toplam Birikim': round(birikim),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(kalan_faizli_borc_toplam)
        })
        
        tum_yukumlulukler_bitti = all(b['tutar'] <= 1 and b.get('kalan_ay', 0) <= 0 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER'])
        
        if tum_yukumlulukler_bitti:
             break
        
        ay_sayisi += 1
        tarih += relativedelta(months=1)
        
    # Yorumlama için ilk ay verilerini ekliyoruz
    ilk_ay_toplam_gider = ZORUNLU_SABIT_GIDER + EV_KREDISI_TAKSIT + okul_taksidi_gider + sabit_taksitli_kredi_toplam + ilk_ay_min_odeme
    
    return {
        "df": pd.DataFrame(aylik_sonuclar),
        "ay_sayisi": ay_sayisi,
        "toplam_faiz": round(toplam_faiz_maliyeti),
        "toplam_birikim": round(sum(ay['Toplam Birikim'] for ay in aylik_sonuclar)),
        "baslangic_faizli_borc": round(baslangic_faizli_borc),
        "ilk_ay_gelir": ilk_ay_toplam_gelir,
        "ilk_ay_gider": ilk_ay_toplam_gider
    }

# ----------------------------------------------------------------------
# 4. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ
# ----------------------------------------------------------------------

def format_tl(value):
    """Değeri Türk Lirası formatına çevirir."""
    # locale.currency ile TL formatını kullanıyoruz
    return locale.currency(value, grouping=True, symbol="₺", international=False)

def yap_finansal_yorum(oran, birikim_hedefi):
    """Gelir/Gider oranına göre dinamik yorum yapar."""
    
    if oran >= 1.05: # Giderler geliri %5 veya daha fazla aşıyor
        return ("🔴 **KRİTİK DURUM: Finansal Boğulma Riski!**", 
                "Aylık zorunlu giderleriniz (min. borç ödemeleri dahil) gelirinizin **üzerindedir**. Bu durum acil nakit akışı sorununa yol açacaktır. **Gelirleri artırmak** veya zorunlu **sabit giderleri acilen kısmak** zorundasınız. Bu senaryoda ek borç ödemesi imkansızdır.")
    
    elif oran >= 0.95: # Giderler gelirin %95-105'i arasında (Başabaş)
        return ("🟠 **YÜKSEK RİSK: Başabaş Noktası!**", 
                f"Aylık gelirinizin %{oran*100:,.0f}'ü zorunlu giderlere gitmektedir. Çok dar bir marjınız var. En ufak bir ek harcama veya aksilik sizi **negatif nakit akışına** itebilir. **'{birikim_hedefi}'** gibi bir birikim hedefi çok zorlu olacaktır. Ek ödeme gücünüz çok düşüktür.")
                
    elif oran >= 0.70: # Giderler gelirin %70-95'i arasında (Borç yükü ağır)
        return ("🟡 **ZORLU DENGE: Ağır Borç Yükü!**", 
                f"Gelirinizin %{oran*100:,.0f}'ü temel ve zorunlu ödemelere ayrılıyor. Borç kapatma süreci **uzun ve yorucu** olacaktır. Borç bitene kadar harcamalarınızı ciddi şekilde kontrol etmeli ve **Tek Seferlik Gelirleri** (ikramiye vb.) tamamen borç kapatmaya yönlendirmelisiniz.")
        
    elif oran >= 0.50: # Giderler gelirin %50-70'i arasında (Yönetilebilir)
        return ("🟢 **YÖNETİLEBİLİR YÜK: Dengeli Durum**", 
                f"Gelirinizin %{oran*100:,.0f}'si zorunlu giderlere gidiyor. Borç yükünüz yönetilebilir seviyededir ve **Yumuşak** stratejide bile makul sürede borçlarınızı kapatabilirsiniz. **Dengeli** stratejiyi seçerek faiz maliyetinizi düşürmeniz önerilir.")
        
    else: # Giderler gelirin %50'sinden az (Konforlu)
        return ("🔵 **KONFORLU FİNANS: Güçlü Durum**", 
                f"Gelirinizin sadece %{oran*100:,.0f}'i zorunlu ödemelere gidiyor. **Çok güçlü bir nakit akışınız** var. **Saldırgan** stratejiyi seçerek faiz maliyetinizi minimuma indirin ve borç biter bitmez yüksek birikime geçin. Ek birikim hedefinizi artırmayı düşünebilirsiniz.")


if calculate_button:
    
    if st.session_state.borclar and st.session_state.gelirler:
        
        st.markdown("---")
        st.markdown("## 🎯 Simülasyon Sonuçları ve Strateji Karşılaştırması")
        
        results = {}
        # Tüm stratejileri tek tek çalıştır
        for name, carpan in STRATEJILER.items():
            results[name] = simule_borc_planı(
                st.session_state.borclar, 
                st.session_state.gelirler,
                carpan
            )
            
        # -------------------------------------------------------------
        # 4.1. FİNANSAL YORUM SİSTEMİ
        # -------------------------------------------------------------
        
        # İlk ayki verileri al
        ilk_sonuc = results[list(results.keys())[0]]
        ilk_ay_gider = ilk_sonuc["ilk_ay_gider"]
        ilk_ay_gelir = ilk_sonuc["ilk_ay_gelir"]
        
        # Gelir/Gider Oranını Hesapla (Min. Ödemeler dahil)
        gelir_gider_oran = ilk_ay_gider / ilk_ay_gelir if ilk_ay_gelir > 0 else 10.0 # Gelir 0'sa yüksek oran ver
        
        yorum_baslik, yorum_detay = yap_finansal_yorum(gelir_gider_oran, format_tl(AYLIK_ZORUNLU_BIRIKIM))
        
        st.subheader("Finansal Durum Analizi (Gelir/Gider Oranına Göre)")
        
        st.markdown(yorum_baslik)
        st.info(f"Mevcut aylık Gelir (Başlangıç): **{format_tl(ilk_ay_gelir)}**\n\nMevcut aylık Zorunlu Giderler (Min. Borç Ödeme Dahil): **{format_tl(ilk_ay_gider)}**\n\n**Gelir/Gider Oranı**: **%{gelir_gider_oran*100:,.1f}**")
        st.write(yorum_detay)
        
        st.markdown("---")
        
        # -------------------------------------------------------------
        # 4.2. KARŞILAŞTIRMA TABLOSU
        # -------------------------------------------------------------
        
        df_karsilastirma = pd.DataFrame({
            "Strateji": list(results.keys()),
            "Borç Kapatma Süresi (Ay)": [r["ay_sayisi"] for r in results.values()],
            "Toplam Faiz Maliyeti": [format_tl(r["toplam_faiz"]) for r in results.values()],
            "Toplam Birikim (Borçlar Kapanana Kadar)": [format_tl(r["toplam_birikim"]) for r in results.values()],
        })
        
        st.subheader("Farklı Stratejilerin Finansal Etkileri")
        st.dataframe(df_karsilastirma.set_index("Strateji"), use_container_width=True)
        
        # -------------------------------------------------------------
        # 4.3. HEDEF KIYASLAMA VE ÖZET YORUM
        # -------------------------------------------------------------
        
        en_hizli_sure = df_karsilastirma["Borç Kapatma Süresi (Ay)"].min()
        en_hizli_strateji = df_karsilastirma.loc[df_karsilastirma["Borç Kapatma Süresi (Ay)"] == en_hizli_sure, "Strateji"].iloc[0]
        
        # Hedef Tarih Hesaplama
        aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
        hedef_ay_no = aylar_map.get(HEDEF_BITIS_TARIHI.split()[0])
        hedef_yil_no = int(HEDEF_BITIS_TARIHI.split()[1])
        hedef_tarih = datetime(hedef_yil_no, hedef_ay_no, 1)
        
        kapanis_tarihi = sim_baslangic_tarihi + relativedelta(months=en_hizli_sure)
        
        st.markdown("\n**Özet Finansal Kapanış Yorumu**")
        
        if kapanis_tarihi <= hedef_tarih:
            sure_farki = relativedelta(hedef_tarih, kapanis_tarihi)
            fark_str = f"{sure_farki.years} yıl {sure_farki.months} ay" if sure_farki.years > 0 else f"{sure_farki.months} ay"
            st.success(f"En hızlı strateji olan **{en_hizli_strateji}** ile borçlarınız hedeflenen **{HEDEF_BITIS_TARIHI}** tarihinden **{fark_str}** *daha erken* kapatılıyor.")
        else:
            sure_farki = relativedelta(kapanis_tarihi, hedef_tarih)
            fark_str = f"{sure_farki.years} yıl {sure_farki.months} ay" if sure_farki.years > 0 else f"{sure_farki.months} ay"
            st.warning(f"En hızlı strateji olan **{en_hizli_strateji}** ile bile borç kapatma tarihi **{kapanis_tarihi.strftime('%Y-%m')}**, hedeflenen **{HEDEF_BITIS_TARIHI}** tarihinden **{fark_str}** *daha geç* gerçekleşiyor. **Finansal Durum Analizi** bölümündeki tavsiyeleri dikkate alınız.")
            
        # -------------------------------------------------------------
        # 4.4. DETAYLI TABLO SEÇİMİ
        # -------------------------------------------------------------
        
        st.markdown("---")
        st.subheader("Aylık Detay Tablosu")
        secili_strateji = st.selectbox("Hangi Stratejinin Aylık Detaylarını Görmek İstersiniz?", options=list(results.keys()))
        
        # Seçilen stratejinin detay tablosunu göster
        st.dataframe(results[secili_strateji]["df"], use_container_width=True)


    else:
        st.warning("Lütfen simülasyonu başlatmak için en az bir gelir ve bir yükümlülük ekleyin.")
