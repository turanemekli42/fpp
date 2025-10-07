import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import numpy as np

# ======================================================================
# 0. STREAMLIT OTURUM DURUMUNU BAŞLATMA
# ======================================================================

# Simülasyon motorunun kullanacağı borç listesini oturumda tutuyoruz
if 'borclar' not in st.session_state:
    st.session_state.borclar = []

# ======================================================================
# 1. STREAMLIT KULLANICI GİRİŞLERİ (SEKMELER)
# ======================================================================

st.set_page_config(layout="wide")
st.title("Finansal Borç Yönetimi Simülasyon Projesi")
st.markdown("---")
tab1, tab2 = st.tabs(["📊 Simülasyon Verileri", "⚙️ Yönetici Kuralları"])

# Varsayılan Değerler
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
    YASAL_FAIZ_AYLIK = st.number_input("Yasal Faiz Oranı (Aylık %)", value=5.0, step=0.05, min_value=0.0) / 100.0
    KK_ASGARI_YUZDESI = st.number_input("KK Asgari Ödeme Anapara Yüzdesi", value=5.0, step=1.0, min_value=0.0) / 100.0
    
    # Yönetici değişkenlerini sabitle
    MAAS_1_ZAM_ORANI = 1 + (zam_yuzdesi_1 / 100.0)
    MAAS_2_ZAM_ORANI = 1 + (zam_yuzdesi_2 / 100.0)

# --------------------------------------------------
# Simülasyon Girişleri Sekmesi (tab1)
# --------------------------------------------------
with tab1:
    st.header("Gelir ve Sabit Giderler")

    col1, col2, col3 = st.columns(3)
    with col1:
        GELIR_MAAS_1 = st.number_input("Maaş 1 (Net)", value=DEFAULT_MAAS_1, step=1000, min_value=0)
        ZORUNLU_SABIT_GIDER = st.number_input("Diğer Sabit Giderler", value=20000, step=1000, min_value=0)
    with col2:
        GELIR_MAAS_2 = st.number_input("Maaş 2 (Net)", value=DEFAULT_MAAS_2, step=1000, min_value=0)
        EV_KREDISI_TAKSIT = st.number_input("Ev Kredisi Taksiti", value=15000, step=1000, min_value=0)
    with col3:
        TEK_SEFERLIK_GELIR = st.number_input("Tek Seferlik Gelir (İlk Ay)", value=100000, step=1000, min_value=0)
        SIM_BASLANGIC_AYI = st.selectbox("Simülasyon Başlangıç Ayı", 
                                            options=["Ekim 2025", "Kasım 2025", "Aralık 2025"], index=0)

    st.markdown("---")
    st.subheader("Sabit ve Okul Giderleri")
    colA, colB, colC = st.columns(3)
    with colA:
        OKUL_TAKSIDI = st.number_input("Okul Taksidi (Aylık)", value=10000, step=1000, min_value=0)
    with colB:
        OKUL_KALAN_AY = st.number_input("Okul Taksidi Kalan Ay", value=12, min_value=0)
    with colC:
        st.markdown("*(Okul taksitleri genellikle taksit süresince sabit kalır)*")

    # ======================================================================
    # 1.1. YENİ: DİNAMİK BORÇ EKLEME ARAYÜZÜ
    # ======================================================================
    st.markdown("---")
    st.subheader("Borçları Yönet")

    # Borç Ekleme Fonksiyonu
    def add_debt(isim, tutar, oncelik, borc_tipi, sabit_taksit, kalan_ay):
        # Borç tipine göre minimum kuralı belirleme mantığı
        if borc_tipi == "Kredi Kartı":
            min_kural = "ASGARI_FAIZ" # Faiz + Yönetici Asgari Yüzdesi
            oncelik = oncelik 
        elif borc_tipi == "Ek Hesap":
            min_kural = "FAIZ" # Sadece Faiz ödemesi
            oncelik = oncelik
        elif borc_tipi == "Kredi (Sabit Taksit)":
            min_kural = "SABIT_TAKSIT"
            # Sabit taksitli borçların önceliği genelde düşüktür (Örn: > 10)
            oncelik = max(10, oncelik) 
            tutar = sabit_taksit * kalan_ay # Anapara tutarı olarak hesaplanır
        elif borc_tipi == "Diğer (Yüksek Asgari Ödeme)":
            min_kural = "ASGARI_44K" # Yüksek sabit min ödeme
            oncelik = oncelik
        else: # Kendi Adı (Genel olarak Faiz)
            min_kural = "FAIZ"
            oncelik = oncelik
        
        # Eğer Sabit Kredi ise, taksit ve kalan ay bilgilerini borç nesnesine ekle
        ek_bilgiler = {}
        if min_kural == "SABIT_TAKSIT":
             ek_bilgiler = {"sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay}
        else:
             ek_bilgiler = {"kalan_ay": 1} # Diğerleri için kalan ay 1 olarak tutulabilir
        
        # Yeni borç nesnesini oluştur
        new_debt = {
            "isim": isim,
            "tutar": tutar,
            "min_kural": min_kural,
            "oncelik": oncelik,
            **ek_bilgiler
        }

        st.session_state.borclar.append(new_debt)
        st.success(f"'{isim}' borcu başarıyla eklendi (Kural: {min_kural}, Öncelik: {oncelik})")

    # Borç Ekleme Formu
    with st.form("new_debt_form", clear_on_submit=True):
        st.markdown("#### Yeni Borç Ekle")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            debt_name = st.text_input("Borç Adı (Örn: Yapı Kredi KK, Taşıt Kredisi)", value="Yeni Borç")
            debt_type = st.selectbox("Borç Tipi", 
                                    ["Kredi Kartı", "Kredi (Sabit Taksit)", "Ek Hesap", "Diğer (Yüksek Asgari Ödeme)", "Kendi Adın (Faizli)"])
            debt_priority = st.number_input("Öncelik Değeri (1 en yüksek öncelik)", min_value=1, value=5)
            
        with col_f2:
            initial_tutar = st.number_input("Kalan Borç Anaparası (TL)", min_value=0.01, value=50000.0)
            
            # Kredi (Sabit Taksit) seçeneğine özel girişler
            if debt_type == "Kredi (Sabit Taksit)":
                debt_taksit = st.number_input("Aylık Sabit Taksit Tutarı", min_value=1.0, value=5000.0)
                debt_kalan_ay = st.number_input("Kalan Taksit Ayı", min_value=1, value=12)
            else:
                debt_taksit = 0.0
                debt_kalan_ay = 1 # Sabit taksitli olmayanlar için bu değerin bir önemi yok

        # Formu gönderme butonu
        submit_button = st.form_submit_button(label="Borcu Ekle")
        if submit_button:
            # Sabit Kredi ise tutarı taksit * kalan ay olarak hesapla
            final_tutar = debt_taksit * debt_kalan_ay if debt_type == "Kredi (Sabit Taksit)" else initial_tutar
            
            add_debt(debt_name, final_tutar, debt_priority, debt_type, debt_taksit, debt_kalan_ay)

    # ------------------------------------------------------------------
    # Eklenen Borçları Göster ve Silme Seçeneği Sun
    # ------------------------------------------------------------------
    if st.session_state.borclar:
        st.markdown("#### Eklenen Borçlarınız")
        
        # Borçları önceliğe göre sıralayıp göster
        sorted_debts = sorted(st.session_state.borclar, key=lambda x: x['oncelik'])
        
        debt_data = []
        for i, debt in enumerate(sorted_debts):
             tutar_gosterim = f"₺{debt['tutar']:,.0f}" if debt['min_kural'] != 'SABIT_TAKSIT' else f"₺{debt['sabit_taksit']:,.0f} x {debt['kalan_ay']} ay"
             debt_data.append({
                 "Borç Adı": debt['isim'],
                 "Öncelik": debt['oncelik'],
                 "Kural": debt['min_kural'],
                 "Kalan Tutar / Yapı": tutar_gosterim,
                 "Sil": f"Sil {i}" 
             })
        
        debt_df = pd.DataFrame(debt_data)
        st.dataframe(debt_df, use_container_width=True, hide_index=True)
        
        # Silme butonu ekle
        st.markdown("---")
        st.markdown("**Borç Silme**")
        debt_to_delete = st.selectbox("Silinecek Borcu Seçin", options=[d['isim'] for d in sorted_debts] + ["Yok"], index=len(sorted_debts))
        
        if st.button(f"'{debt_to_delete}' Borcunu Sil") and debt_to_delete != "Yok":
            # Silmek için borcun ismini bul
            st.session_state.borclar = [d for d in st.session_state.borclar if d['isim'] != debt_to_delete]
            st.warning(f"'{debt_to_delete}' borcu silindi. Tekrar hesaplayın.")
            # Sayfayı yeniden yükle
            st.rerun()


    # ------------------------------------------------------------------
    # HESAPLA BUTONU BURADA
    # ------------------------------------------------------------------
    st.markdown("---")
    # Borç listesi boşsa butonu devre dışı bırak
    is_disabled = not bool(st.session_state.borclar)
    calculate_button = st.button("HESAPLA VE PLANI OLUŞTUR", type="primary", disabled=is_disabled)


# ----------------------------------------------------------------------
# 2. YARDIMCI FONKSIYONLAR (Minimum Ödeme Hesaplama Mantığı)
# ----------------------------------------------------------------------

def hesapla_min_odeme(borc, faiz_orani, kk_asgari_yuzdesi):
    """Her bir borç için minimum ödeme tutarını kurala ve yönetici ayarlarına göre hesaplar."""
    tutar = borc['tutar']
    kural = borc['min_kural']
    
    ASGARI_44K_DEGERI = 45000 
    
    if tutar <= 0: return 0

    if kural == "FAIZ":
        # Ek Hesap / Genel Faizli Borç: Sadece faiz ödenir (Faiz çığına uygun)
        return tutar * faiz_orani
    
    elif kural == "ASGARI_44K":
        # Yüksek sabit minimum ödeme
        return min(tutar, ASGARI_44K_DEGERI) 
        
    elif kural == "ASGARI_FAIZ":
        # Kredi Kartı: Faiz + Yönetici Paneli Anapara Yüzdesi
        return (tutar * faiz_orani) + (tutar * kk_asgari_yuzdesi)
        
    elif kural == "SABIT_TAKSIT":
        # Kredi: Sabit taksit ödenir
        if borc.get('kalan_ay', 0) > 0:
             return borc.get('sabit_taksit', 0)
        return 0
        
    return 0

# ----------------------------------------------------------------------
# 3. SIMÜLASYON MOTORU
# ----------------------------------------------------------------------

def simule_borc_planı(borclar_listesi, kk_asgari_yuzdesi, faiz_aylik, zam_1_oran, zam_2_oran):
    
    aylik_sonuclar = []
    mevcut_borclar = [b.copy() for b in borclar_listesi] 
    
    ay_str = SIM_BASLANGIC_AYI.split()
    tarih = datetime(int(ay_str[1]), {"Ekim": 10, "Kasım": 11, "Aralık": 12}[ay_str[0]], 1)
    
    ay_sayisi = 0
    max_iterasyon = 60 # Simülasyonu 5 yıla çıkardık

    while ay_sayisi < max_iterasyon:
        
        ay_adi = tarih.strftime("%Y-%m")
        
        # 3.1. Gelir ve Sabit Gider Güncellemesi
        maas_1 = GELIR_MAAS_1 * (zam_1_oran if tarih.year >= 2026 else 1.0)
        maas_2 = GELIR_MAAS_2 * (zam_2_oran if tarih.year >= 2026 else 1.0)
        toplam_gelir = maas_1 + maas_2
        
        zorunlu_gider_toplam = ZORUNLU_SABIT_GIDER + EV_KREDISI_TAKSIT
        
        # Okul Taksidi Kontrolü
        okul_taksidi_gider = 0
        if ay_sayisi < OKUL_KALAN_AY:
            okul_taksidi_gider = OKUL_TAKSIDI
            zorunlu_gider_toplam += okul_taksidi_gider
        
        # Sabit Kredilerin Taksitleri (Borç listesi içinden dinamik olarak çekilir)
        sabit_kredi_taksit_toplam = 0
        for borc in mevcut_borclar:
            if borc['min_kural'] == 'SABIT_TAKSIT' and borc.get('kalan_ay', 0) > 0:
                 sabit_kredi_taksit_toplam += borc.get('sabit_taksit', 0)
                 
        
        # 3.2. Minimum Borç Ödemeleri Hesaplama
        
        min_odeme_toplam = 0
        for borc in mevcut_borclar:
            if borc['tutar'] > 0:
                min_odeme_toplam += hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)
        
        # 3.3. Saldırı Gücü (Attack Power) Hesaplama
        
        # Toplam Giderler = Sabit Giderler + Sabit Kredi Taksitleri + Min. Borç Ödemeleri
        giderler_dahil_min_odeme = zorunlu_gider_toplam + sabit_kredi_taksit_toplam + min_odeme_toplam
        kalan_nakit = toplam_gelir - giderler_dahil_min_odeme
        saldırı_gucu = max(0, kalan_nakit) 
        
        tek_seferlik_kullanilan = 0
        if ay_adi == SIM_BASLANGIC_AYI.replace(" ", "-").split("-")[1] + "-" + SIM_BASLANGIC_AYI.split(" ")[0][:3]:
             saldırı_gucu += TEK_SEFERLIK_GELIR
             tek_seferlik_kullanilan = TEK_SEFERLIK_GELIR
             
        # Borç Kapatma Kontrolü
        yuksek_oncelikli_borclar_kaldi = any(b['tutar'] > 1 for b in mevcut_borclar if b['min_kural'] != 'SABIT_TAKSIT')

        birikim = 0
        if not yuksek_oncelikli_borclar_kaldi and kalan_nakit > 0:
             # Borçlar bittiyse (Sabit Taksitliler hariç), kalan nakitin %90'ı birikime gider
             birikim = kalan_nakit * 0.90
             saldırı_gucu = kalan_nakit * 0.10 
             
        # 3.4. Borçlara Ödeme Uygulama (Faiz Çığı)
        
        saldırı_kalan = saldırı_gucu
        kapanan_borclar_listesi = []
        
        # a) Faiz Ekleme ve Minimum Ödeme Düşme
        for borc in mevcut_borclar:
            if borc['tutar'] > 0:
                min_odeme = hesapla_min_odeme(borc, faiz_aylik, kk_asgari_yuzdesi)
                
                # Sabit Taksitli Kredilerin anaparasına faiz eklenmez, sadece taksit ödenir
                if borc['min_kural'] != 'SABIT_TAKSIT':
                    borc['tutar'] += borc['tutar'] * faiz_aylik 
                    borc['tutar'] -= min_odeme 
                else: # Sabit Taksitli Kredi
                    # Sadece taksit, anaparadan düşülür
                    taksit = borc.get('sabit_taksit', 0)
                    
                    # Basit yaklaşımla, tüm taksiti anaparadan düşelim ve kalan ayı azaltalım.
                    # Gerçekçi faiz/anapara ayrımı için banka amortisman tablosu gerekir.
                    borc['tutar'] -= taksit 
                    borc['kalan_ay'] = max(0, borc['kalan_ay'] - 1)
                
        # b) Saldırı Gücünü Uygulama
        # Borçları önceliğe göre sırala (Faiz Çığı Yöntemi)
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            if borc['tutar'] > 1 and saldırı_kalan > 0 and borc['min_kural'] != 'SABIT_TAKSIT':
                # Sabit taksitli borçlara saldırı gücü uygulanmaz, otomatik taksit ödenir
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
            'Sabit Giderler': round(zorunlu_gider_toplam + sabit_kredi_taksit_toplam),
            'Min. Borç Ödemeleri (Faiz Çığının Serbest Bıraktığı)': round(min_odeme_toplam),
            'Borç Saldırı Gücü (Ek Ödeme)': round(saldırı_gucu - saldırı_kalan),
            'Birikim (Hedef)': round(birikim),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Borç Toplam': round(kalan_borc_toplam)
        })
        
        # Tüm yüksek öncelikli borçlar bittiyse ve Sabit Kredilerin kalan ayı bittiyse durdur
        sabit_krediler_kaldi = any(b['kalan_ay'] > 0 for b in mevcut_borclar if b['min_kural'] == 'SABIT_TAKSIT')
        
        if kalan_borc_toplam <= 1 and not sabit_krediler_kaldi:
             break
        
        ay_sayisi += 1
        tarih += relativedelta(months=1)

    return pd.DataFrame(aylik_sonuclar)

# ----------------------------------------------------------------------
# 4. PROGRAMI ÇALIŞTIRMA VE ÇIKTI GÖSTERİMİ
# ----------------------------------------------------------------------

if calculate_button:
    
    if st.session_state.borclar:
        # Simülasyonu çalıştır
        borc_tablosu = simule_borc_planı(
            st.session_state.borclar, # Dinamik borç listesini al
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
            st.dataframe(borc_tablosu, use_container_width=True)
        else:
            st.warning("Girdiğiniz değerlerle bir sonuç üretilemedi. Lütfen giderlerin gelirlerden yüksek olmadığından emin olun.")
    else:
        st.warning("Lütfen simülasyonu başlatmak için en az bir borç ekleyin.")
