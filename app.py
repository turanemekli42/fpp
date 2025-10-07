import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np

# ======================================================================
# 0. STREAMLIT OTURUM DURUMUNU BAŞLATMA
# ======================================================================

# Simülasyon motorunun kullanacağı borç ve gelir listesini oturumda tutuyoruz
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

# Varsayılanlar
DEFAULT_BASLANGIC_AYI = "Ocak 2025" # Simülasyon başlangıcı için genel bir ay

# --------------------------------------------------
# Yönetici Kuralları Sekmesi (tab2)
# --------------------------------------------------
with tab2:
    st.header("Simülasyon Kurallarını Yönet")
    st.markdown("⚠️ **Dikkat:** Buradaki ayarlamalar tüm hesaplama mantığını kökten değiştirir.")

    st.subheader("Faiz ve Borç Kapatma Kuralları")
    YASAL_FAIZ_AYLIK = st.number_input("Yasal Faiz Oranı (Aylık %)", value=5.0, step=0.05, min_value=0.0) / 100.0
    KK_ASGARI_YUZDESI = st.number_input("KK Asgari Ödeme Anapara Yüzdesi", value=5.0, step=1.0, min_value=0.0) / 100.0
    

# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1)
# --------------------------------------------------
with tab1:
    st.header("Genel Ayarlar ve Sabit Giderler")

    col1, col2 = st.columns([1, 2])
    with col1:
        SIM_BASLANGIC_AYI = st.selectbox("Simülasyon Başlangıç Ayı", 
                                            options=["Ekim 2025", "Kasım 2025", "Aralık 2025"], index=0)
    with col2:
        ZORUNLU_SABIT_GIDER = st.number_input("Diğer Sabit Giderler (Ev Kirası, Fatura vb.)", value=20000, step=1000, min_value=0)
        EV_KREDISI_TAKSIT = st.number_input("Ev Kredisi Taksiti (Borç değilse)", value=15000, step=1000, min_value=0)

    # ======================================================================
    # 1.1. YENİ: DİNAMİK GELİR EKLEME ARAYÜZÜ
    # ======================================================================
    st.markdown("---")
    st.subheader("Gelir Kaynaklarını Yönet")
    
    # Yardımcı Fonksiyon: Gelir Ekle
    def add_income(isim, tutar, tip, zam_yuzdesi, zam_ayi_gun):
        # Gelir Tipi ve Kurallarını Belirle
        if tip == "Maaş":
            periyot = "Aylık"
            artış_kuralı = "Yıllık Zam"
            artış_oranı = 1 + (zam_yuzdesi / 100.0)
        elif tip == "Sabit Kira Geliri":
            periyot = "Aylık"
            artış_kuralı = "Yıllık Zam"
            artış_oranı = 1 + (zam_yuzdesi / 100.0)
        elif tip == "Tek Seferlik Gelir (İkramiye)":
            periyot = "Tek Seferlik"
            artış_kuralı = "-"
            artış_oranı = 1.0
            zam_yuzdesi = 0 # Yüzde sıfırla
        else: # Diğer
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
            "zam_ayi_gun": zam_ayi_gun, # Zam ayını (Örn: Ocak) tutuyoruz
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
                zam_yuzdesi = st.number_input("Yıllık Zam Yüzdesi (Örn: 30)", value=30.0, min_value=0.0)
                zam_ayi = st.selectbox("Yıllık Zam Ayı", options=["Ocak", "Temmuz", "Haziran"], index=0)
            
            if income_type == "Tek Seferlik Gelir (İkramiye)":
                 zam_ayi = st.selectbox("Tek Seferlik Gelirin Geldiği Ay", options=["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"], index=3)


        submit_income_button = st.form_submit_button(label="Geliri Ekle")
        if submit_income_button:
            add_income(income_name, initial_tutar, income_type, zam_yuzdesi, zam_ayi)


    # Eklenen Gelirleri Göster ve Silme Seçeneği Sun
    if st.session_state.gelirler:
        st.markdown("#### Eklenen Gelir Kaynaklarınız")
        
        income_data = []
        for i, income in enumerate(st.session_state.gelirler):
             income_data.append({
                 "Gelir Adı": income['isim'],
                 "Tip": income['tip'],
                 "Başlangıç Tutarı": f"₺{income['baslangic_tutar']:,.0f}",
                 "Artış Kuralı": f"{income['zam_yuzdesi']}% her {income['zam_ayi_gun']}" if income['tip'] in ["Maaş", "Sabit Kira Geliri"] else income['periyot'],
                 "Sil": f"Sil {i}" 
             })
        
        income_df = pd.DataFrame(income_data)
        st.dataframe(income_df, use_container_width=True, hide_index=True)
        
        # Silme butonu ekle
        st.markdown("---")
        income_to_delete = st.selectbox("Silinecek Gelir Kaynağını Seçin", options=[d['isim'] for d in st.session_state.gelirler] + ["Yok"], index=len(st.session_state.gelirler))
        
        if st.button(f"'{income_to_delete}' Gelirini Sil"):
            if income_to_delete != "Yok":
                st.session_state.gelirler = [d for d in st.session_state.gelirler if d['isim'] != income_to_delete]
                st.warning(f"'{income_to_delete}' geliri silindi. Tekrar hesaplayın.")
                st.rerun()


    # ======================================================================
    # 1.2. BORÇ EKLEME ARAYÜZÜ
    # ======================================================================
    st.markdown("---")
    st.subheader("Borçları ve Sabit Taksitli Yükümlülükleri Yönet")
    # Borç Ekleme Fonksiyonu (Önceki Adımdan Aynı Kaldı)
    # ... (kod devam eder, borç ekleme formu ve görüntüleme)
    
    # Borç Ekleme Fonksiyonu
    def add_debt(isim, tutar, oncelik, borc_tipi, sabit_taksit, kalan_ay):
        if borc_tipi == "Kredi Kartı":
            min_kural = "ASGARI_FAIZ" 
            oncelik = oncelik 
        elif borc_tipi == "Ek Hesap":
            min_kural = "FAIZ" 
            oncelik = oncelik
        elif borc_tipi == "Okul/Eğitim Taksidi":
            min_kural = "SABIT_TAKSIT_GIDER"
            oncelik = max(100, oncelik)
            tutar = 0
        elif borc_tipi == "Kredi (Sabit Taksit)":
            min_kural = "SABIT_TAKSIT_ANAPARA" 
            oncelik = max(10, oncelik) 
        elif borc_tipi == "Diğer (Yüksek Asgari Ödeme)":
            min_kural = "ASGARI_44K" 
            oncelik = oncelik
        else:
            min_kural = "FAIZ"
            oncelik = oncelik
        
        ek_bilgiler = {}
        if min_kural.startswith("SABIT_TAKSIT"):
             ek_bilgiler = {"sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay}
             if min_kural == "SABIT_TAKSIT_ANAPARA":
                 final_tutar = tutar
             else:
                 final_tutar = 0 
        else:
             ek_bilgiler = {"kalan_ay": 1}
             final_tutar = tutar
        
        new_debt = {
            "isim": isim,
            "tutar": final_tutar,
            "min_kural": min_kural,
            "oncelik": oncelik,
            **ek_bilgiler
        }
        st.session_state.borclar.append(new_debt)
        st.success(f"'{isim}' borcu başarıyla eklendi (Kural: {min_kural}, Öncelik: {oncelik})")

    # Borç Ekleme Formu
    with st.form("new_debt_form", clear_on_submit=True):
        st.markdown("#### Yeni Yükümlülük Ekle")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı (Örn: Taşıt Kredisi, 2026 Okul Taksidi)", value="Yeni Yükümlülük")
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

        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        if submit_button:
            tutar_girisi = initial_tutar
            add_debt(debt_name, tutar_girisi, debt_priority, debt_type, debt_taksit, debt_kalan_ay)

    # Eklenen Borçları Göster ve Silme Seçeneği Sun
    if st.session_state.borclar:
        st.markdown("#### Eklenen Yükümlülükleriniz (Önceliğe Göre Sıralı)")
        sorted_debts = sorted(st.session_state.borclar, key=lambda x: x['oncelik'])
        debt_data = []
        for i, debt in enumerate(sorted_debts):
             tutar_gosterim = f"₺{debt['tutar']:,.0f}" if debt['min_kural'] not in ['SABIT_TAKSIT_ANAPARA', 'SABIT_TAKSIT_GIDER'] else (f"₺{debt['tutar']:,.0f} Kalan" if debt['tutar'] > 0 else "Gider Kalemi")
             
             if debt['min_kural'].startswith("SABIT_TAKSIT"):
                 ek_bilgi = f"Taksit: ₺{debt.get('sabit_taksit', 0):,.0f} x {debt.get('kalan_ay', 0)} ay"
             else:
                 ek_bilgi = "Min Ödeme Kuralı Uygulanır"

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
        
        if st.button(f"'{debt_to_delete}' Yükümlülüğünü Sil"):
            if debt_to_delete != "Yok":
                st.session_state.borclar = [d for d in st.session_state.borclar if d['isim'] != debt_to_delete]
                st.warning(f"'{debt_to_delete}' yükümlülüğü silindi. Tekrar hesaplayın.")
                st.rerun()


    # ------------------------------------------------------------------
    # HESAPLA BUTONU BURADA
    # ------------------------------------------------------------------
    st.markdown("---")
    is_disabled = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button = st.button("HESAPLA VE PLANI OLUŞTUR", type="primary", disabled=is_disabled)


# ----------------------------------------------------------------------
# 2. YARDIMCI FONKSIYONLAR (Minimum Ödeme Hesaplama Mantığı)
# ----------------------------------------------------------------------

def hesapla_min_odeme(borc, faiz_orani, kk_asgari_yuzdesi):
    """Her bir borç için minimum ödeme tutarını kurala ve yönetici ayarlarına göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    
    ASGARI_44K_DEGERI = 45000 
    
    if tutar <= 0 and not kural.endswith("_GIDER"): return 0
    if kural == "SABIT_TAKSIT_GIDER":
        if borc.get('kalan_ay', 0) > 0:
            return borc.get('sabit_taksit', 0)
        return 0

    if kural == "FAIZ":
        return tutar * faiz_orani
    
    elif kural == "ASGARI_44K":
        return min(tutar, ASGARI_44K_DEGERI) 
        
    elif kural == "ASGARI_FAIZ":
        return (tutar * faiz_orani) + (tutar * kk_asgari_yuzdesi)
        
    elif kural == "SABIT_TAKSIT_ANAPARA":
        if borc.get('kalan_ay', 0) > 0:
             return borc.get('sabit_taksit', 0)
        return 0
        
    return 0
    
def hesapla_aylik_gelir(gelir_listesi, mevcut_tarih, sim_baslangic_tarihi):
    """Verilen aya göre tüm gelir kalemlerinin toplamını hesaplar."""
    
    toplam_gelir = 0
    
    # Ay isimlerini Türkçe'den İngilizce'ye çeviren map (tarih karşılaştırması için)
    aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
    
    for gelir in gelir_listesi:
        gelir_tutari = gelir['baslangic_tutar']
        
        if gelir['tip'] == "Tek Seferlik Gelir (İkramiye)":
            # Tek seferlik gelir, sadece belirtilen ayda gelir
            zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
            
            if mevcut_tarih.month == zam_ay_no and mevcut_tarih.year == sim_baslangic_tarihi.year:
                toplam_gelir += gelir_tutari
                
        else:
            # Yıllık Zam/Sabit Gelirler
            
            if gelir['artış_kuralı'] == "Yıllık Zam":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                
                # Zam geçmişte kalmışsa (simülasyon başlangıcından önce), başlangıç tutarını güncelleyerek başla
                if sim_baslangic_tarihi.month > zam_ay_no and sim_baslangic_tarihi.year == mevcut_tarih.year:
                    # Basitçe, başlangıç ayından önceki zammın uygulanmış olduğunu varsayalım
                    # Bu noktada detaylı zam hesaplaması yerine, simülasyon içindeki aylık mantığı kullanacağız
                    pass
                
                # Zam Ayı geldi mi?
                if mevcut_tarih.month == zam_ay_no and mevcut_tarih.year > sim_baslangic_tarihi.year:
                    # Yıllık zam, her yıl belirlenen ayda uygulanır
                    # NOT: Bu basit modelde, her maaşın başlangıç tutarı artış oranına göre güncellenmelidir.
                    # Simülasyon motoru içinde dinamik olarak tutar bilgisini güncellemeliyiz.
                    
                    # *Basitleştirilmiş Zam Mantığı:* Sadece ilk yılın zam ayında zammı uygula
                    # Gerçekçi zam için, simülasyon döngüsü içinde bu tutarı tutan bir mekanizma gerekir.
                    pass # Şimdilik simülasyon motorunda güncelleyeceğiz

            toplam_gelir += gelir_tutari
            
    return toplam_gelir
    

# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU
# ----------------------------------------------------------------------

def simule_borc_planı(borclar_listesi, gelirler_listesi, kk_asgari_yuzdesi, faiz_aylik):
    
    aylik_sonuclar = []
    mevcut_borclar = [b.copy() for b in borclar_listesi] 
    mevcut_gelirler = [g.copy() for g in gelirler_listesi] # Dinamik gelirler için mutable liste
    
    ay_str = SIM_BASLANGIC_AYI.split()
    sim_baslangic_tarihi = datetime(int(ay_str[1]), {"Ocak":1,"Şubat":2,"Mart":3,"Nisan":4,"Mayıs":5,"Haziran":6,"Temmuz":7,"Ağustos":8,"Eylül":9,"Ekim": 10, "Kasım": 11, "Aralık": 12}[ay_str[0]], 1)
    tarih = sim_baslangic_tarihi
    
    ay_sayisi = 0
    max_iterasyon = 60

    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Dinamik Gelir Hesaplama ve Zam Uygulama
        toplam_gelir = 0
        zam_yapıldı_bu_ay = False
        aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
        
        tek_seferlik_kullanilan = 0

        for gelir in mevcut_gelirler:
            gelir_tutari = gelir['baslangic_tutar']
            
            if gelir['tip'] == "Tek Seferlik Gelir (İkramiye)":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                if tarih.month == zam_ay_no and tarih.year == sim_baslangic_tarihi.year:
                    toplam_gelir += gelir_tutari
                    tek_seferlik_kullanilan += gelir_tutari
                    
            elif gelir['artış_kuralı'] == "Yıllık Zam":
                zam_ay_no = aylar_map.get(gelir['zam_ayi_gun'])
                
                # Eğer zam ayı geldiyse ve bu bir zam yılıysa
                if tarih.month == zam_ay_no and (tarih.year > sim_baslangic_tarihi.year or (tarih.year == sim_baslangic_tarihi.year and ay_sayisi == 0)):
                    if tarih.year > sim_baslangic_tarihi.year: # İlk yılın ilk ayında zam yapılmaz
                        artış_oranı = 1 + (gelir['zam_yuzdesi'] / 100.0)
                        gelir['baslangic_tutar'] = gelir_tutari * artış_oranı
                        gelir_tutari = gelir['baslangic_tutar']
                        zam_yapıldı_bu_ay = True
                        
                toplam_gelir += gelir_tutari

            else:
                # Sabit Gelirler
                toplam_gelir += gelir_tutari
        
        
        # Diğer Zorunlu Giderler (Hala statik)
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
                    min_odeme_toplam += hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)

        
        # 3.3. Saldırı Gücü (Attack Power) Hesaplama
        giderler_dahil_min_odeme = zorunlu_gider_toplam + sabit_taksitli_kredi_toplam + min_odeme_toplam
        kalan_nakit = toplam_gelir - giderler_dahil_min_odeme
        saldırı_gucu = max(0, kalan_nakit) 
        
        # Tek seferlik gelir zaten toplam gelire eklendi, burada ekstra eklemeye gerek yok.
             
        # Borç Kapatma Kontrolü
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER', 'SABIT_TAKSIT_ANAPARA'])

        birikim = 0
        if not yuksek_oncelikli_borclar_kaldi and kalan_nakit > 0:
             birikim = kalan_nakit * 0.90
             saldırı_gucu = kalan_nakit * 0.10 
             
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
                    min_odeme = hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)
                    borc['tutar'] += borc['tutar'] * faiz_aylik 
                    borc['tutar'] -= min_odeme 
                    
        # b) Saldırı Gücünü Uygulama
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
        
        kalan_borc_toplam = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER'])
        
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir),
            'Toplam Sabit Giderler': round(zorunlu_gider_toplam + sabit_taksitli_kredi_toplam),
            'Min. Borç Ödemeleri (Faiz Çığının Serbest Bıraktığı)': round(min_odeme_toplam),
            'Borç Saldırı Gücü (Ek Ödeme)': round(saldırı_gucu - saldırı_kalan),
            'Birikim (Hedef)': round(birikim),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(kalan_borc_toplam)
        })
        
        tum_yukumlulukler_bitti = all(b['tutar'] <= 1 and b.get('kalan_ay', 0) <= 0 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_TAKSIT_GIDER'])
        
        if tum_yukumlulukler_bitti:
             break
        
        ay_sayisi += 1
        tarih += relativedelta(months=1)

    return pd.DataFrame(aylik_sonuclar)

# ----------------------------------------------------------------------
# 4. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ
# ----------------------------------------------------------------------

if calculate_button:
    
    if st.session_state.borclar and st.session_state.gelirler:
        
        borc_tablosu = simule_borc_planı(
            st.session_state.borclar, 
            st.session_state.gelirler, # Yeni: Gelir listesini gönderiyoruz
            KK_ASGARI_YUZDESI, 
            YASAL_FAIZ_AYLIK
        )

        st.markdown("---")
        st.markdown("## 🎯 Simülasyon Sonuçları")
        
        if not borc_tablosu.empty:
            kapanis_ayi = borc_tablosu['Ay'].iloc[-1]
            st.success(f"🎉 **TEBRİKLER!** Faizli borçlarınız bu senaryoya göre **{kapanis_ayi}** ayında kapatılıyor.")
            st.markdown("### Aylık Nakit Akışı ve Borç Kapatma Tablosu")
            st.dataframe(borc_tablosu, use_container_width=True)
        else:
            st.error("Girdiğiniz değerlerle bir sonuç üretilemedi. Lütfen gelirlerin giderlerden yüksek olduğundan emin olun.")
    else:
        st.warning("Lütfen simülasyonu başlatmak için en az bir gelir ve bir yükümlülük ekleyin.")
