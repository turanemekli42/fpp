import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np

# ======================================================================
# 1. STREAMLIT KULLANICI GİRİŞLERİ (SEKMELER)
# ======================================================================

st.title("Finansal Borç Yönetimi Simülasyon Projesi")
st.markdown("---")
tab1, tab2 = st.tabs(["📊 Simülasyon Verileri", "⚙️ Yönetici Kuralları"])

# Varsayılan Değerler (Anonimleştirilmiş Örnekler)
DEFAULT_MAAS_1 = 80000
DEFAULT_MAAS_2 = 50000

# --------------------------------------------------
# Yönetici Kuralları Sekmesi (tab2)
# --------------------------------------------------
with tab2:
    st.header("Simülasyon Kurallarını Yönet")
    st.markdown("⚠️ **Dikkat:** Buradaki ayarlamalar tüm hesaplama mantığını kökten değiştirir.")

    # Zam Oranları
    st.subheader("Maaş Zammı Ayarları (Ocak 2026)")
    zam_yuzdesi_1 = st.number_input("Maaş 1 Zam Yüzdesi (Örn: 30)", value=30.0, step=1.0)
    zam_yuzdesi_2 = st.number_input("Maaş 2 Zam Yüzdesi (Örn: 10)", value=10.0, step=1.0)
    
    # Faiz ve Asgari Ödeme Kuralları
    st.subheader("Faiz ve Borç Kapatma Kuralları")
    YASAL_FAIZ_AYLIK = st.number_input("Yasal Faiz Oranı (Aylık %)", value=5.0, step=0.05) / 100.0
    KK_ASGARI_YUZDESI = st.number_input("KK Asgari Ödeme Anapara Yüzdesi", value=5.0, step=1.0) / 100.0
    
    # Yönetici değişkenlerini sabitle
    MAAS_1_ZAM_ORANI = 1 + (zam_yuzdesi_1 / 100.0)
    MAAS_2_ZAM_ORANI = 1 + (zam_yuzdesi_2 / 100.0)

# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1)
# --------------------------------------------------
with tab1:
    st.header("Gelir ve Sabit Giderler")

    # Temel Gelir ve Giderler
    GELIR_MAAS_1 = st.number_input("Maaş 1 (Net)", value=DEFAULT_MAAS_1, step=1000)
    GELIR_MAAS_2 = st.number_input("Maaş 2 (Net)", value=DEFAULT_MAAS_2, step=1000)
    TEK_SEFERLIK_GELIR = st.number_input("Tek Seferlik Gelir (İlk Ay)", value=100000, step=1000)
    SIM_BASLANGIC_AYI = st.selectbox("Simülasyon Başlangıç Ayı", 
                                        options=["Ekim 2025", "Kasım 2025", "Aralık 2025"], index=0)

    # Zorunlu Sabit Giderler
    ZORUNLU_SABIT_GIDER = st.number_input("Diğer Sabit Giderler", value=20000, step=1000)
    EV_KREDISI_TAKSIT = st.number_input("Ev Kredisi Taksiti", value=15000, step=1000)
    OKUL_TAKSIDI = st.number_input("Okul Taksidi (Aylık)", value=10000, step=1000)
    OKUL_KALAN_AY = st.number_input("Okul Taksidi Kalan Ay", value=12, min_value=0)
    
    # Sabit Kredi Örnekleri (Anonimleştirildi)
    SABIT_KREDI_TAKSIT = st.number_input("Sabit Taksitli Kredi Taksiti", value=15000, step=1000)
    SABIT_KREDI_KALAN_AY = st.number_input("Sabit Taksitli Kredi Kalan Ay", value=15, min_value=0)

    # Dinamik Borç Girişi
    st.subheader("Yüksek Öncelikli Borçlar (Kredi Kartı / Ek Hesap)")
    borc_sayisi = st.number_input("Kaç adet yüksek öncelikli borç var?", min_value=1, max_value=10, value=3)

    borclar_input = []
    # Yeni Anonim Varsayılan Borçlar
    default_borclar = [
        ("KK_1_Faizli", 120000.0, 1, "FAIZ"),
        ("KK_2_Asgari", 80000.0, 2, "ASGARI_FAIZ"),
        ("Ek_Hsp_1", 50000.0, 3, "FAIZ"),
    ]

    for i in range(borc_sayisi):
        st.markdown(f"---")
        d_isim, d_tutar, d_oncelik, d_kural = default_borclar[i] if i < len(default_borclar) else (f"Borç_{i+1}", 100000.0, i+1, "FAIZ")
        
        isim = st.text_input(f"Borç {i+1} Adı", value=d_isim, key=f'isim_{i}')
        tutar = st.number_input(f"Borç {i+1} Kalan Tutar (TL)", value=d_tutar, step=5000.0, key=f'tutar_{i}')
        oncelik = st.number_input(f"Borç {i+1} Öncelik (1 en yüksek)", min_value=1, value=d_oncelik, key=f'oncelik_{i}')
        kural = st.selectbox(f"Borç {i+1} Minimum Kuralı", ["ASGARI_44K", "FAIZ", "ASGARI_FAIZ"], index=(["ASGARI_44K", "FAIZ", "ASGARI_FAIZ"].index(d_kural) if d_kural in ["ASGARI_44K", "FAIZ", "ASGARI_FAIZ"] else 1), key=f'kural_{i}')
        
        borclar_input.append({
            "isim": isim, 
            "tutar": tutar, 
            "min_kural": kural, 
            "oncelik": oncelik, 
            "kalan_ay": 1 
        })

    # Sabit Taksitli Kredileri ve Ek Hesapları Ekleyin (Kişisel Banka Adları Kaldırıldı)
    borclar_input.append({"isim": "Sabit_Kredi_1", "tutar": SABIT_KREDI_TAKSIT * SABIT_KREDI_KALAN_AY, "min_kural": "SABIT_TAKSIT", "oncelik": 7, "kalan_ay": SABIT_KREDI_KALAN_AY})
    borclar_input.append({"isim": "Kucuk_Kredi_Son_Taksit", "tutar": 1500.0, "min_kural": "SABIT_TAKSIT", "oncelik": 8, "kalan_ay": 1})
    
    # ------------------------------------------------------------------
    # HESAPLA BUTONU
    # ------------------------------------------------------------------
    st.markdown("---")
    calculate_button = st.button("HESAPLA VE PLANI OLUŞTUR", type="primary")


# ----------------------------------------------------------------------
# 2. YARDIMCI FONKSIYONLAR (Minimum Ödeme Hesaplama Mantığı)
# ----------------------------------------------------------------------

def hesapla_min_odeme(borc, faiz_orani, kk_asgari_yuzdesi):
    """Her bir borç için minimum ödeme tutarını kurala ve yönetici ayarlarına göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    
    # GLOBAL SABİT: Kredi kartı için sabit %40 kuralının temsili (gerçek veriden arındırıldı)
    ASGARI_44K_DEGERI = 45000 
    
    if tutar <= 0: return 0

    if kural == "FAIZ":
        return tutar * faiz_orani
    
    elif kural == "ASGARI_44K":
        # Yüksek minimum ödeme gerektiren kredi kartı/borç senaryosu
        return min(tutar, ASGARI_44K_DEGERI) 
        
    elif kural == "ASGARI_FAIZ":
        # Faiz + Yönetici Panelinden gelen Anapara Yüzdesi kullanılır
        return (tutar * faiz_orani) + (tutar * kk_asgari_yuzdesi)
        
    elif kural == "SABIT_TAKSIT":
        if borc['isim'] == "Sabit_Kredi_1" and borc['kalan_ay'] > 0:
            return SABIT_KREDI_TAKSIT
        elif borc['isim'] == "Kucuk_Kredi_Son_Taksit" and borc['kalan_ay'] > 0:
             return borc['tutar'] 
        return 0
        
    return 0

# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU
# ----------------------------------------------------------------------

def simule_borc_planı(borclar, kk_asgari_yuzdesi, faiz_aylik, zam_1_oran, zam_2_oran):
    
    aylik_sonuclar = []
    mevcut_borclar = [b.copy() for b in borclar] 
    
    ay_str = SIM_BASLANGIC_AYI.split()
    tarih = datetime(int(ay_str[1]), {"Ekim": 10, "Kasım": 11, "Aralık": 12}[ay_str[0]], 1)
    
    ay_sayisi = 0
    max_iterasyon = 36 

    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Gelir ve Sabit Gider Güncellemesi
        
        maas_1 = GELIR_MAAS_1 * (zam_1_oran if tarih.year >= 2026 else 1.0)
        maas_2 = GELIR_MAAS_2 * (zam_2_oran if tarih.year >= 2026 else 1.0)
        toplam_gelir = maas_1 + maas_2
        
        zorunlu_gider_toplam = ZORUNLU_SABIT_GIDER + EV_KREDISI_TAKSIT
        
        okul_taksidi_gider = 0
        if ay_sayisi < OKUL_KALAN_AY:
            okul_taksidi_gider = OKUL_TAKSIDI
            zorunlu_gider_toplam += okul_taksidi_gider

        # Sabit Kredi Taksiti Kontrolü
        sabit_kredi_gider = 0
        sabit_kredi_obj = next((b for b in mevcut_borclar if b['isim'] == "Sabit_Kredi_1"), None)
        if sabit_kredi_obj and sabit_kredi_obj['kalan_ay'] > 0:
             sabit_kredi_gider = SABIT_KREDI_TAKSIT
             
        
        # 3.2. Minimum Borç Ödemeleri Hesaplama
        
        min_odeme_toplam = 0
        for borc in mevcut_borclar:
            if borc['tutar'] > 0:
                min_odeme_toplam += hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)
        
        # 3.3. Saldırı Gücü (Attack Power) Hesaplama
        
        giderler_dahil_min_odeme = zorunlu_gider_toplam + sabit_kredi_gider + min_odeme_toplam
        kalan_nakit = toplam_gelir - giderler_dahil_min_odeme
        saldırı_gucu = max(0, kalan_nakit) 
        
        tek_seferlik_kullanilan = 0
        if ay_adi == SIM_BASLANGIC_AYI.replace(" ", "-").split("-")[1] + "-" + SIM_BASLANGIC_AYI.split(" ")[0][:3]:
             saldırı_gucu += TEK_SEFERLIK_GELIR
             tek_seferlik_kullanilan = TEK_SEFERLIK_GELIR
             
        # Birikim Kontrolü
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['oncelik'] < 7 and b['min_kural'] != 'SABIT_TAKSIT')

        birikim = 0
        if not yuksek_oncelikli_borclar_kaldi and kalan_nakit > 0:
             birikim = kalan_nakit * 0.90
             saldırı_gucu = kalan_nakit * 0.10 
             
        # 3.4. Borçlara Ödeme Uygulama (Faiz Çığı)
        
        saldırı_kalan = saldırı_gucu
        kapanan_borclar_listesi = []
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 0:
                min_odeme = hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)
                
                borc['tutar'] += borc['tutar'] * faiz_aylik 
                borc['tutar'] -= min_odeme 
                
                if borc['min_kural'] == 'SABIT_TAKSIT' and borc['kalan_ay'] > 0:
                     borc['kalan_ay'] = max(0, borc['kalan_ay'] - 1)
                     
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 1 and saldırı_kalan > 0:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0

        # 3.5. Sonuçları Kaydetme ve Döngü Kontrolü
        
        kalan_borc_toplam = sum(b['tutar'] for b in mevcut_borclar)
        
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir + (tek_seferlik_kullanilan if tek_seferlik_kullanilan else 0)),
            'Sabit Giderler': round(giderler_dahil_min_odeme - min_odeme_toplam),
            'Min. Borç Ödemeleri': round(min_odeme_toplam),
            'Borç Saldırı Gücü': round(saldırı_gucu - saldırı_kalan),
            'Birikim (Hedef)': round(birikim),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Borç Toplam': round(kalan_borc_toplam)
        })
        
        if kalan_borc_toplam <= 1 and not yuksek_oncelikli_borclar_kaldi and ay_sayisi > SABIT_KREDI_KALAN_AY + OKUL_KALAN_AY:
             break
        
        ay_sayisi += 1
        tarih += relativedelta(months=1)


    return pd.DataFrame(aylik_sonuclar)

# ----------------------------------------------------------------------
# 4. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ (Butona Bağlandı)
# ----------------------------------------------------------------------

if calculate_button:
    
    # Simülasyonu çalıştır
    borc_tablosu = simule_borc_planı(
        borclar_input, 
        KK_ASGARI_YUZDESI, 
        YASAL_FAIZ_AYLIK, 
        MAAS_1_ZAM_ORANI, 
        MAAS_2_ZAM_ORANI
    )

    # Sonuçları göster
    st.markdown("---")
    st.markdown("## 🎯 Simülasyon Sonuçları")
    
    if not borc_tablosu.empty:
        kapanis_ayi = borc_tablosu['Ay'].iloc[-1]
        st.success(f"🎉 **TEBRİKLER!** Borçlar, bu senaryoya göre **{kapanis_ayi}** ayında kapatılıyor.")
        st.markdown("### Aylık Nakit Akışı ve Borç Kapatma Tablosu")
        st.dataframe(borc_tablosu)
    else:
        st.warning("Girdiğiniz değerlerle bir sonuç üretilemedi. Lütfen giderlerin gelirlerden yüksek olmadığından emin olun.")
