import pandas as pd
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import locale
import matplotlib.pyplot as plt

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

# Varsayılan Kurlar ve Değerler (UX kolaylığı için)
DEFAULT_BIRIM_DEGERLERI = {
    "TL (Nakit/Vadeli Mevduat)": 1.0,
    "Gram Altın": 2500.0,
    "Dolar (USD)": 32.5,
    "Euro (EUR)": 35.0,
    "Diğer": 1.0
}

# Varsayılan Stratejiler (Gelişmiş Mod ve Yönetici Kuralları için)
STRATEJILER = {
    "Yumuşak (Düşük Ek Ödeme)": 0.2,
    "Dengeli (Orta Ek Ödeme)": 0.5,
    "Saldırgan (Maksimum Ek Ödeme)": 1.0
}
FAIZ_STRATEJILERI = {
    "İyimser Faiz (x0.8)": 0.8,
    "Normal Faiz (x1.0)": 1.0,
    "Kötümser Faiz (x1.2)": 1.2
}
ONCELIK_STRATEJILERI = {
    "Kullanıcı Belirler": "Kullanici",
    "Borç Kartopu (Snowball)": "Kartopu",
    "Borç Çığı (Avalanche)": "Avcilik"
}

st.set_page_config(layout="wide") 

if 'borclar' not in st.session_state:
    st.session_state.borclar = []
if 'gelirler' not in st.session_state:
    st.session_state.gelirler = []
if 'tek_seferlik_gelir_isaretleyicisi' not in st.session_state:
    st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

# ======================================================================
# 1. YARDIMCI FONKSİYONLAR
# ======================================================================

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
    
# --------------------------------------------------
# Gelir Ekleme Fonksiyonu
# --------------------------------------------------
def add_income(isim, tutar, artış_kuralı, artış_yuzdesi, periyot_ay, zam_ayi_gun):
    
    if artış_kuralı == "Sabit (Artış Yok)":
        periyot = "Aylık"
        artış_oranı = 1.0
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
        "periyot_ay": periyot_ay 
    }
    st.session_state.gelirler.append(new_income)
    st.success(f"'{isim}' geliri başarıyla eklendi.")

# --------------------------------------------------
# Borç Ekleme Fonksiyonu (Dinamik Öncelik Yönetimi)
# --------------------------------------------------
def add_debt(isim, faizli_anapara, oncelik_str, borc_tipi, sabit_taksit, kalan_ay, faiz_aylik, kk_asgari_yuzdesi, zorunlu_anapara_yuzdesi):
    
    borc_listesi = []
    final_priority = 1 # Varsayılan: Sabit giderler ve ilk borçlar için

    # 1. Borç Önceliğini Ayarla (Sadece ek ödemeye açık borçlar için)
    if isinstance(oncelik_str, str) and oncelik_str:
        
        ek_odemeye_acik_borclar_info = [
            (b['isim'], b['oncelik']) for b in st.session_state.borclar 
            if b.get('min_kural') not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
        ]
        current_priorities = sorted([b['oncelik'] for b in st.session_state.borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']])
        
        if "En Yüksek Öncelik" in oncelik_str:
            for borc in st.session_state.borclar:
                borc['oncelik'] += 1
            new_priority = 1
        elif "En Sona Bırak" in oncelik_str:
            max_priority = max(current_priorities) if current_priorities else 0
            new_priority = max_priority + 1
        else:
            hedef_borc_ismi = oncelik_str.split('. ')[1].split("'den sonra")[0]
            hedef_oncelik = next((b['oncelik'] for b in st.session_state.borclar if b['isim'] == hedef_borc_ismi), max(current_priorities) + 1 if current_priorities else 1)
            
            new_priority = hedef_oncelik + 1 
            
            for borc in st.session_state.borclar:
                if borc['oncelik'] >= new_priority:
                    borc['oncelik'] += 1
            
        final_priority = new_priority

    # 2. Borç Objektlerini Oluşturma
    if borc_tipi == "Kredi Kartı":
        # 1. KK Taksitli Alışverişler (Gider olarak)
        if sabit_taksit > 0 and kalan_ay > 0:
            borc_listesi.append({
                "isim": f"{isim} (Taksitler)",
                "tutar": 0, "min_kural": "SABIT_TAKSIT_GIDER",
                "oncelik": 1, "sabit_taksit": sabit_taksit,
                "kalan_ay": kalan_ay, "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
            })
        
        # 2. KK Dönem Borcu (Faizli)
        if faizli_anapara > 0:
             borc_listesi.append({
                "isim": f"{isim} (Dönem Borcu)",
                "tutar": faizli_anapara, "min_kural": "ASGARI_FAIZ", 
                "oncelik": final_priority + 1000, # Taksitlerden sonra başlar, ek ödeme için atanır
                "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": kk_asgari_yuzdesi,
                "kalan_ay": 99999
            })
    
    elif borc_tipi == "Ek Hesap (KMH)":
         borc_listesi.append({
            "isim": isim, "tutar": faizli_anapara,
            "min_kural": "FAIZ_ART_ANAPARA", "oncelik": final_priority,
            "faiz_aylik": faiz_aylik, "zorunlu_anapara_yuzdesi": zorunlu_anapara_yuzdesi,
            "kalan_ay": 99999
        })

    elif borc_tipi in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]:
        borc_listesi.append({
            "isim": isim, "tutar": 0, "min_kural": "SABIT_GIDER", "oncelik": 1,
            "sabit_taksit": sabit_taksit, "kalan_ay": 99999,
            "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
        })
        
    elif borc_tipi == "Kredi (Sabit Taksit)":
         borc_listesi.append({
            "isim": isim, "tutar": faizli_anapara, 
            "min_kural": "SABIT_TAKSIT_ANAPARA", "oncelik": final_priority,
            "sabit_taksit": sabit_taksit, "kalan_ay": kalan_ay,
            "faiz_aylik": 0, "kk_asgari_yuzdesi": 0
        })
        
    elif borc_tipi == "Diğer Faizli Borç":
         borc_listesi.append({
            "isim": isim, "tutar": faizli_anapara, 
            "min_kural": "FAIZ", "oncelik": final_priority,
            "faiz_aylik": faiz_aylik, "kk_asgari_yuzdesi": 0, "kalan_ay": 99999
        })
        
    
    if borc_listesi:
        st.session_state.borclar.extend(borc_listesi)
        st.success(f"'{isim}' yükümlülüğü başarıyla eklendi. Öncelik: {final_priority}")

# ======================================================================
# 2. SİMÜLASYON MOTORU (FAİZ ÇIĞI/KARTOPU MANTIĞI EKLENDİ)
# ======================================================================

def simule_borc_planı(borclar_listesi, gelirler_listesi, agresiflik_carpani, faiz_carpani, hedef_tipi, aylik_min_birikim, toplam_birikim_hedefi, oncelik_amaci, birikim_araci, aylik_artis_yuzdesi, oncelik_stratejisi):
    
    aylik_sonuclar = []
    mevcut_borclar = [b.copy() for b in borclar_listesi] 
    mevcut_gelirler = [g.copy() for g in gelirler_listesi] 
    
    aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}
    sim_baslangic_tarihi = datetime.now().replace(day=1) 
    tarih = sim_baslangic_tarihi
    
    ay_sayisi = 0
    max_iterasyon = 60
    toplam_faiz_maliyeti = 0 
    
    baslangic_faizli_borc = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
    
    # Birikim Değerleme Ayarları
    aylik_artis_carpani = 1 + (aylik_artis_yuzdesi / 100.0)
    birikim_araci_miktari = 0.0
    BIRIM_BASLANGIC_DEGERI = DEFAULT_BIRIM_DEGERLERI.get(birikim_araci, 1.0)
    guncel_birikim_birim_degeri = BIRIM_BASLANGIC_DEGERI 
    mevcut_birikim = 0.0
    
    # *** BORÇ KAPATMA STRATEJİSİ (Otomatik Sıralama) ***
    if oncelik_stratejisi == "Kartopu":
        ek_odemeye_aciklar = [b for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']]
        ek_odemeye_aciklar.sort(key=lambda x: x['tutar']) # Küçükten Büyüğe (Kartopu)
        for i, borc in enumerate(ek_odemeye_aciklar): borc['oncelik'] = i + 1
    elif oncelik_stratejisi == "Avcilik":
        ek_odemeye_aciklar = [b for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']]
        ek_odemeye_aciklar.sort(key=lambda x: x.get('faiz_aylik', 0), reverse=True) # Faiz Oranına göre (Çığı)
        for i, borc in enumerate(ek_odemeye_aciklar): borc['oncelik'] = i + 1

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
                 
            else: 
                toplam_gelir += gelir_tutari
        
        if ay_sayisi == 0:
            ilk_ay_toplam_gelir = toplam_gelir
        
        # 3.2. Yükümlülük Ödemeleri
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
            if hedef_tipi == "Aylık Sabit Tutar":
                hedef_birikim_aylik = aylik_min_birikim
            else: 
                kalan_ay_sayisi = max_iterasyon - ay_sayisi
                kalan_birikim_hedefi = max(0, toplam_birikim_hedefi - mevcut_birikim)
                hedef_birikim_aylik = kalan_birikim_hedefi / kalan_ay_sayisi if kalan_ay_sayisi > 0 else kalan_birikim_hedefi
            
            if oncelik_amaci == "Borç Kapatma Hızını Maksimize Et":
                birikime_ayrilan = kalan_nakit * (1 - agresiflik_carpani)
                saldırı_gucu = kalan_nakit * agresiflik_carpani
            else: 
                # Birikim Hedefine Ulaşmayı Garanti Et
                birikime_ayrilan = min(kalan_nakit, hedef_birikim_aylik)
                kalan_nakit -= birikime_ayrilan
                saldırı_gucu = kalan_nakit * agresiflik_carpani
        else:
            birikime_ayrilan = kalan_nakit
            saldırı_gucu = 0
            
        # 3.5. Birikim Değerleme ve Güncelleme
        guncel_birikim_birim_degeri *= aylik_artis_carpani
        
        if guncel_birikim_birim_degeri > 0:
            eklenen_birim_miktar = birikime_ayrilan / guncel_birikim_birim_degeri
            birikim_araci_miktari += eklenen_birim_miktar
        
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
                         min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                         borc['tutar'] -= min_odeme
            else: # Faizli borçlar için
                if borc['tutar'] > 0:
                    etkilenen_faiz_orani = borc['faiz_aylik'] * faiz_carpani
                    eklenen_faiz = borc['tutar'] * etkilenen_faiz_orani 
                    toplam_faiz_maliyeti += eklenen_faiz
                    
                    min_odeme = hesapla_min_odeme(borc, faiz_carpani)
                    borc['tutar'] += eklenen_faiz 
                    borc['tutar'] -= min_odeme 
                    
        # b) Saldırı Gücünü Uygulama (Önceliğe Göre Sıralama)
        mevcut_borclar.sort(key=lambda x: x['oncelik'])
        
        for borc in mevcut_borclar:
            is_ek_odemeye_acik = borc['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER']
            
            if borc['tutar'] > 1 and saldırı_kalan > 0 and is_ek_odemeye_acik:
                odecek_tutar = min(saldırı_kalan, borc['tutar'])
                borc['tutar'] -= odecek_tutar
                saldırı_kalan -= odecek_tutar
                
                if borc['tutar'] <= 1:
                     kapanan_borclar_listesi.append(borc['isim'])
                     borc['tutar'] = 0

        # 3.7. Sonuçları Kaydetme
        kalan_faizli_borc_toplam = sum(b['tutar'] for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER', 'SABIT_TAKSIT_GIDER'])
        
        aylik_sonuclar.append({
            'Ay': ay_adi,
            'Toplam Gelir': round(toplam_gelir),
            'Toplam Zorunlu Giderler': round(zorunlu_gider_toplam),
            'Min. Borç Ödemeleri': round(min_borc_odeme_toplam),
            'Borç Saldırı Gücü': round(saldırı_gucu),
            'Aylık Birikim Katkısı': round(birikime_ayrilan),
            'Kapanan Borçlar': ', '.join(kapanan_borclar_listesi) if kapanan_borclar_listesi else '-',
            'Kalan Faizli Borç Toplamı': round(kalan_faizli_borc_toplam),
            'Toplam Birikim': round(mevcut_birikim)
        })
        
        tum_yukumlulukler_bitti = all(b['tutar'] <= 1 and b.get('kalan_ay', 0) <= 0 for b in mevcut_borclar if b['min_kural'] not in ['SABIT_GIDER'])
        
        if tum_yukumlulukler_bitti: break
        
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


# ======================================================================
# 3. GELİŞMİŞ/BASİT MOD ARAYÜZÜ (UX Revizyonu)
# ======================================================================

st.title("Finansal Borç Yönetimi ve Simülasyon Aracı")
st.markdown("---")
aylar_tr = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
sim_bas_yil = datetime.now().year
aylar_map = {"Ocak": 1, "Şubat": 2, "Mart": 3, "Nisan": 4, "Mayıs": 5, "Haziran": 6, "Temmuz": 7, "Ağustos": 8, "Eylül": 9, "Ekim": 10, "Kasım": 11, "Aralık": 12}


tab_basic, tab_advanced, tab_rules = st.tabs(["✨ Basit Planlama", "📊 Gelişmiş Simülasyon", "⚙️ Yönetici Kuralları"])

# --------------------------------------------------
# 3.1. GELİR/BORÇ EKLEME FORMLARI (KOŞULLU GÖSTERİM DAHİL)
# --------------------------------------------------

def render_income_form(context):
    st.subheader(f"Gelir Kaynaklarını Yönet ({context})")
    with st.form(f"new_income_form_{context}", clear_on_submit=True):
        col_g1, col_g2 = st.columns(2) 
        with col_g1:
            income_name = st.text_input("Gelir Kaynağı Adı", value="Ana Maaş", key=f'inc_name_{context}')
            initial_tutar = st.number_input("Başlangıç Net Tutarı (TL)", min_value=1.0, value=80000.0, key=f'inc_tutar_{context}')
            
        with col_g2:
            if context == 'Basit':
                artış_kuralı = "Yıllık Zam"
                st.markdown(f"**Artış Kuralı:** Yıllık Zam")
                artış_yuzdesi = 35.0
                zam_ayi = aylar_tr[0]
                periyot_ay = 12
                st.markdown(f"**Artış Yüzdesi:** %{artış_yuzdesi}")
                st.markdown(f"**Zam Ayı:** {zam_ayi}")
            else:
                artış_kuralı = st.selectbox("Gelir Artış Kuralı", ["Sabit (Artış Yok)", "Yıllık Zam", "Dönemlik Zam", "Tek Seferlik Ödeme"], key=f'inc_kural_{context}')
                
                artış_yuzdesi = 0.0
                zam_ayi = ""
                periyot_ay = 12
                
                if artış_kuralı in ["Yıllık Zam", "Dönemlik Zam"]:
                    artış_yuzdesi = st.number_input("Artış Yüzdesi (Örn: 30)", value=30.0, min_value=0.0, key=f'inc_zam_yuzdesi_{context}')

                if artış_kuralı == "Yıllık Zam":
                    zam_ayi = st.selectbox("Yıllık Artış Ayı", options=aylar_tr, index=0, key=f'inc_zam_ayi_{context}')
                    
                elif artış_kuralı == "Dönemlik Zam":
                     periyot_ay = st.selectbox("Artış Sıklığı (Ayda Bir)", options=[3, 6, 9], index=1, key=f'inc_donemlik_periyot_{context}')
                
                elif artış_kuralı == "Tek Seferlik Ödeme":
                     zam_ayi = st.selectbox("Gelirin Geleceği Ay", options=aylar_tr, index=9, key=f'inc_tek_seferlik_ayi_{context}')
            
        submit_income_button = st.form_submit_button(label="Geliri Ekle")
        if submit_income_button:
            add_income(income_name, initial_tutar, artış_kuralı, artış_yuzdesi, periyot_ay, zam_ayi)

def render_debt_form(context):
    st.subheader(f"Yükümlülükleri/Borçları Yönet ({context})")
    
    with st.form(f"new_debt_form_{context}", clear_on_submit=True):
        col_f1, col_f2, col_f3 = st.columns(3) 
        
        # --- COL F1: Temel Bilgiler ---
        with col_f1:
            debt_name = st.text_input("Yükümlülük Adı", value="Yeni Borç", key=f'debt_name_{context}')
            debt_type = st.selectbox("Yükümlülük Tipi", 
                                     ["Kredi Kartı", "Ek Hesap (KMH)", 
                                      "--- Sabit Giderler ---", 
                                      "Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti",
                                      "--- Sabit Ödemeli Borçlar ---",
                                      "Kredi (Sabit Taksit)", 
                                      "--- Diğer Faizli Borçlar ---",
                                      "Diğer Faizli Borç"], key=f'debt_type_{context}')
            
            # --- Mantık Değişkenleri ---
            is_faizli_borc_ve_ek_odemeli = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Kredi (Sabit Taksit)", "Diğer Faizli Borç"]
            is_faizli_borc = debt_type in ["Kredi Kartı", "Ek Hesap (KMH)", "Diğer Faizli Borç"]
            is_sabit_gider = debt_type in ["Sabit Kira Gideri", "Fatura/Aidat Gideri", "Ev Kredisi Taksiti"]
            is_sabit_kredi = debt_type == "Kredi (Sabit Taksit)"
            is_kk = debt_type == "Kredi Kartı"
            is_kmh = debt_type == "Ek Hesap (KMH)"
            
            # YENİ ÖNCELİK MANTIK BLOĞU (Sadece ek ödemeli borçlar için görünür)
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
            
        # --- COL F2: Tutar ve Süre Bilgileri (Koşullu GÖSTERİM & GRİLEŞTİRME) ---
        with col_f2:
            initial_faizli_tutar = 0.0
            debt_taksit = 0.0
            debt_kalan_ay = 0

            # Faizli Kalan Borç Anaparası
            if is_faizli_borc or is_sabit_kredi:
                 initial_faizli_tutar = st.number_input("Faizli Kalan Borç Anaparası", min_value=0.0, value=50000.0 if not is_sabit_gider else 0.0, key=f'initial_tutar_{context}', disabled=is_sabit_gider)
                
            # Aylık Taksit/Gider Tutarı (Her zaman görünür, alakasızken 0'a çekilir)
            is_taksit_disabled = not (is_sabit_gider or is_sabit_kredi or is_kk)
            default_taksit = 5000.0 if not is_taksit_disabled else 0.0
            debt_taksit = st.number_input("Aylık Zorunlu Taksit/Gider Tutarı", min_value=0.0, value=default_taksit, key=f'sabit_taksit_{context}', disabled=is_taksit_disabled)
            
            # Kredi Kartı Taksit Alanları
            if is_kk:
                st.info("KK taksitleri ve dönem borcu ayrılacaktır.")
                # KK Taksit Aylık Ödeme (Zaten yukarıdaki alanda giriliyor, burayı sadeleştirelim)
                debt_kalan_ay = st.number_input("KK Taksitlerin Ortalama Kalan Ayı", min_value=1, value=12, key=f'kk_taksit_kalan_ay_{context}', disabled=not is_kk)

            # Kredi Kalan Ay Bilgisi
            is_kalan_ay_disabled = not is_sabit_kredi
            if is_sabit_kredi:
                 debt_kalan_ay = st.number_input("Kredi Kalan Taksit Ayı", min_value=1, value=12, key=f'kalan_taksit_ay_{context}', disabled=is_kalan_ay_disabled)
                 
        # --- COL F3: Faiz ve Asgari Ödeme Bilgileri (Koşullu GÖSTERİM & GRİLEŞTİRME) ---
        with col_f3:
            debt_faiz_aylik = 0.0
            debt_kk_asgari_yuzdesi = 0.0
            debt_zorunlu_anapara_yuzdesi = 0.0
            
            # Aylık Faiz Oranı
            is_faiz_disabled = not is_faizli_borc
            faiz_default = 5.0 if not is_faiz_disabled else 0.0
            debt_faiz_aylik = st.number_input("Aylık Faiz Oranı (%)", value=faiz_default, step=0.05, min_value=0.0, key=f'debt_faiz_aylik_{context}', disabled=is_faiz_disabled) / 100.0
                
            # Kredi Kartı Asgari Ödeme
            is_kk_asgari_disabled = not is_kk
            kk_asgari_default = 5.0 if not is_kk_asgari_disabled else 0.0
            debt_kk_asgari_yuzdesi = st.number_input("KK Asgari Ödeme Anapara Yüzdesi (%)", value=kk_asgari_default, step=1.0, min_value=0.0, key=f'kk_asgari_{context}', disabled=is_kk_asgari_disabled) / 100.0
            
            # Ek Hesap Zorunlu Anapara
            is_kmh_anapara_disabled = not is_kmh
            kmh_anapara_default = 5.0 if not is_kmh_anapara_disabled else 0.0
            debt_zorunlu_anapara_yuzdesi = st.number_input("KMH Zorunlu Anapara Kapama Yüzdesi (%)", value=kmh_anapara_default, step=1.0, min_value=0.0, key=f'kmh_anapara_{context}', disabled=is_kmh_anapara_disabled) / 100.0
                
        submit_button = st.form_submit_button(label="Yükümlülüğü Ekle")
        if submit_button:
            # Formun gönderiminde, disabled alanların 0 olması gerektiğini varsayarak gönderiyoruz
            add_debt(debt_name, initial_faizli_tutar, debt_priority_str, debt_type, debt_taksit, debt_kalan_ay, debt_faiz_aylik, debt_kk_asgari_yuzdesi, debt_zorunlu_anapara_yuzdesi)


# --------------------------------------------------
# 3.2. BASİT PLANLAMA MODU (tab_basic)
# --------------------------------------------------
with tab_basic:
    
    st.header("✨ Hızlı ve Varsayılan Planlama")
    st.info("Sadece Gelir ve Borçlarınızı girin. Tüm stratejiler (**Borç Çığı** ve **Saldırgan** ek ödeme) otomatik atanacaktır.")
    
    col_st1, col_st2 = st.columns(2)
    with col_st1:
         BIRIKIM_TIPI_BASIC = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_basic')
         AYLIK_ZORUNLU_BIRIKIM_BASIC = st.number_input("Aylık Zorunlu Birikim Tutarı", value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik_basic', disabled=BIRIKIM_TIPI_BASIC != "Aylık Sabit Tutar")
         TOPLAM_BIRIKIM_HEDEFI_BASIC = st.number_input("Hedef Toplam Birikim Tutarı", value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam_basic', disabled=BIRIKIM_TIPI_BASIC != "Borç Bitimine Kadar Toplam Tutar")
    with col_st2:
        st.markdown(f"**Borç Kapatma Yöntemi:** Borç Çığı (Avalanche)")
        st.markdown(f"**Ek Ödeme Agresifliği:** Saldırgan (Maksimum Ek Ödeme)")
        st.markdown(f"**Birikim Değerlemesi:** TL Mevduat (Aylık %3.5 Artış)")

    
    render_income_form("Basit")
    render_debt_form("Basit")
    
    st.markdown("---")
    is_disabled_basic = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_basic = st.button("BORÇ KAPATMA PLANINI OLUŞTUR", type="primary", disabled=is_disabled_basic)


# --------------------------------------------------
# 3.3. GELİŞMİŞ SİMÜLASYON MODU (tab_advanced)
# --------------------------------------------------
with tab_advanced:
    st.header("📊 Gelişmiş Simülasyon ve Senaryo Analizi")
    
    col_geli1, col_geli2 = st.columns(2)
    with col_geli1:
        # Bu alanlar simülasyon motorunda şu an kullanılmıyor ama UX için tutuldu.
        SIM_BASLANGIC_AYI_ADV = st.selectbox("Simülasyon Başlangıç Ayı", options=[f"{a} {y}" for y in range(2025, 2027) for a in aylar_tr], index=9, key='sim_baslangic_ayi_adv')
        hedef_ay_str = st.selectbox("Hedef Borç Kapatma Ayı", options=aylar_tr, index=5, key='hedef_ay_adv')
        sim_bas_yil = int(SIM_BASLANGIC_AYI_ADV.split()[1])
        hedef_yil = st.number_input("Hedef Borç Kapatma Yılı", min_value=sim_bas_yil, max_value=sim_bas_yil + 5, value=sim_bas_yil + 2, key='hedef_yil_adv')
        
        ONCELIK_AMACI_ADV = st.selectbox("Öncelikli Amaç", 
                               options=["Borç Kapatma Hızını Maksimize Et", "Birikim Hedefine Ulaşmayı Garanti Et"],
                               index=0, key='oncelik_amaci_adv')
        
        ONCELIK_STRATEJISI_ADV = st.selectbox("Borç Kapatma Yöntemi", 
                               options=list(ONCELIK_STRATEJILERI.keys()),
                               index=0, key='oncelik_stratejisi_adv')
        
    with col_geli2:
        BIRIKIM_TIPI_ADV = st.radio("Birikim Hedefi Tipi", ["Aylık Sabit Tutar", "Borç Bitimine Kadar Toplam Tutar"], index=0, key='birikim_tipi_adv')
        AYLIK_ZORUNLU_BIRIKIM_ADV = st.number_input("Aylık Zorunlu Birikim Tutarı", value=5000, step=500, min_value=0, key='zorunlu_birikim_aylik_adv', disabled=BIRIKIM_TIPI_ADV != "Aylık Sabit Tutar")
        TOPLAM_BIRIKIM_HEDEFI_ADV = st.number_input("Hedef Toplam Birikim Tutarı", value=50000, step=5000, min_value=0, key='zorunlu_birikim_toplam_adv', disabled=BIRIKIM_TIPI_ADV != "Borç Bitimine Kadar Toplam Tutar")
        
        BIRIKIM_ARACI_ADV = st.selectbox("Birikimlerin Yönlendirileceği Araç", 
                                     options=list(DEFAULT_BIRIM_DEGERLERI.keys()), 
                                     index=1, key='birikim_araci_adv')
        TAHMINI_AYLIK_ARTIS_YUZDESI_ADV = st.number_input("Tahmini Aylık Değer Artışı (%)", 
                                                       value=1.5, min_value=0.0, step=0.1, 
                                                       key='aylik_artis_yuzdesi_adv',
                                                       help="Referans için Yönetici Kuralları sekmesine bakın.")
        
    render_income_form("Gelişmiş")
    render_debt_form("Gelişmiş")
    
    st.markdown("---")
    is_disabled_adv = not (bool(st.session_state.borclar) and bool(st.session_state.gelirler))
    calculate_button_adv = st.button("TÜM FİNANSAL SENARYOLARI HESAPLA VE KARŞILAŞTIR", type="primary", disabled=is_disabled_adv)

# --------------------------------------------------
# 3.4. YÖNETİCİ KURALLARI MODU (tab_rules)
# --------------------------------------------------
with tab_rules:
    st.header("Simülasyon Kurallarını Yönet")
    
    st.subheader("Borç Kapatma Stratejisi Çarpanları (Agresiflik)")
    st.dataframe(pd.DataFrame(list(STRATEJILER.items()), columns=['Strateji', 'Çarpan']), hide_index=True)
    
    st.markdown("---")
    st.subheader("Faiz Oranı Sapma Senaryoları")
    st.dataframe(pd.DataFrame(list(FAIZ_STRATEJILERI.items()), columns=['Senaryo', 'Çarpan']), hide_index=True)
    
    st.markdown("---")
    st.subheader("Otomatik Öncelik Stratejileri")
    st.markdown("""
        | Strateji | Kriter | Amaç |
        | :--- | :--- | :--- |
        | **Borç Kartopu (Snowball)** | En küçük borçtan başlanır | Psikolojik motivasyon |
        | **Borç Çığı (Avalanche)** | En yüksek faizli borçtan başlanır | Finansal kârı maksimize etmek |
    """)

    st.markdown("---")
    st.subheader("Birikim Değerlemesi Artış Tahmini Referansı")
    st.info("""
        #### 💡 Tahmini Aylık Değer Artışı Referansı
        | Birikim Aracı | Tipik Aylık (%) | Yorum |
        | :--- | :--- | :--- |
        | **TL (Mevduat)** | 2.5% - 4.5% | Banka mevduat faiz getirisine eşittir. |
        | **Döviz (USD/EUR)** | 1.0% - 3.0% | Tahmini kur artış hızına eşittir. |
        | **Altın/Diğer** | 1.5% - 4.0% | Enflasyona karşı koruma beklentisine eşittir. |
    """)

# --------------------------------------------------
# 4. HESAPLAMA VE SONUÇ GÖSTERİMİ
# --------------------------------------------------

def create_comparison_chart(final_df):
    # Kalan Faizli Borç Hızı Grafiği
    st.subheader("1. Kalan Borçların Zamanla Kapanma Hızı Karşılaştırması")
    st.line_chart(final_df, x='Ay', y='Kalan Faizli Borç Toplamı', color='Senaryo', use_container_width=True)
    st.caption("Farklı stratejilerde kalan borç bakiyenizin aylık değişimi. Daha erken sıfıra inen çizgi, daha hızlı borç kapatmayı gösterir.")
    
    # Nakit Akışı Dağılım Grafiği (İlk Ay)
    first_month_data = final_df[final_df['Ay'] == final_df['Ay'].min()]
    
    if not first_month_data.empty:
        st.subheader("2. İlk Ay Nakit Akışı Dağılımı")
        scenario_data = first_month_data[first_month_data['Senaryo'] == first_month_data['Senaryo'].iloc[0]] 
        
        df_nakit = pd.DataFrame({
            'Kategori': ['Zorunlu Giderler', 'Min. Borç Ödemeleri', 'Borç Saldırı Gücü', 'Aylık Birikim Katkısı'],
            'Tutar': [
                scenario_data['Toplam Zorunlu Giderler'].iloc[0],
                scenario_data['Min. Borç Ödemeleri'].iloc[0],
                scenario_data['Borç Saldırı Gücü'].iloc[0],
                scenario_data['Aylık Birikim Katkısı'].iloc[0]
            ]
        })
        # Plotly kullanılarak güzel bir pasta grafiği de eklenebilir. Şimdilik bar chart ile devam edelim.
        st.bar_chart(df_nakit, x='Kategori', y='Tutar', use_container_width=True)
        st.caption(f"Toplam gelir: {format_tl(scenario_data['Toplam Gelir'].iloc[0])}. Borç saldırı gücünüz, kalan nakdinizi gösterir.")
        
    # Birikim ve Borç Dengesi Grafiği
    if final_df['Senaryo'].nunique() == 1:
        st.subheader("3. Borç Kapatma Sonrası Birikim Gelişimi")
        st.line_chart(final_df, x='Ay', y=['Kalan Faizli Borç Toplamı', 'Toplam Birikim'], use_container_width=True)
        st.caption("Çizgilerin kesişim noktası, finansal dönüm noktanızı (tüm borçların bittiği an) gösterir.")


if calculate_button_basic or calculate_button_adv:
    
    if calculate_button_basic:
        # BASİT MOD VARSAYILANLARI
        sim_params = {
            'agresiflik_carpani': 1.0,
            'faiz_carpani': 1.0,
            'hedef_tipi': BIRIKIM_TIPI_BASIC,
            'aylik_min_birikim': AYLIK_ZORUNLU_BIRIKIM_BASIC,
            'toplam_birikim_hedefi': TOPLAM_BIRIKIM_HEDEFI_BASIC,
            'oncelik_amaci': "Borç Kapatma Hızını Maksimize Et",
            'birikim_araci': "TL (Nakit/Vadeli Mevduat)",
            'aylik_artis_yuzdesi': 3.5,
            'oncelik_stratejisi': "Avcilik" # Borç Çığı (En kârlı)
        }
        
        all_scenarios = {}
        result = simule_borc_planı(st.session_state.borclar, st.session_state.gelirler, **sim_params)
        all_scenarios["Basit Plan"] = result
        st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

    elif calculate_button_adv:
        # GELİŞMİŞ MOD AYARLARI
        sim_params = {
            'hedef_tipi': BIRIKIM_TIPI_ADV,
            'aylik_min_birikim': AYLIK_ZORUNLU_BIRIKIM_ADV,
            'toplam_birikim_hedefi': TOPLAM_BIRIKIM_HEDEFI_ADV,
            'oncelik_amaci': ONCELIK_AMACI_ADV,
            'birikim_araci': BIRIKIM_ARACI_ADV,
            'aylik_artis_yuzdesi': TAHMINI_AYLIK_ARTIS_YUZDESI_ADV,
            'oncelik_stratejisi': ONCELIK_STRATEJILERI[ONCELIK_STRATEJISI_ADV]
        }
        
        all_scenarios = {}
        for faiz_name, faiz_carpan in FAIZ_STRATEJILERI.items(): 
            for aggressive_name, aggressive_carpan in STRATEJILER.items(): 
                
                scenario_name = f"{aggressive_name} / {faiz_name}"
                
                result = simule_borc_planı(
                    st.session_state.borclar, 
                    st.session_state.gelirler, 
                    aggressive_carpan, 
                    faiz_carpan,
                    **sim_params
                )
                all_scenarios[scenario_name] = result
                st.session_state.tek_seferlik_gelir_isaretleyicisi = set()

    # --- SONUÇLARIN GÖSTERİMİ ---
    
    st.markdown("## 🎯 Finansal Simülasyon Sonuçları")
    st.markdown("---")
    
    # Karşılaştırma Tablosu
    comparison_data = []
    final_df = pd.DataFrame()
    
    for scenario_name, result in all_scenarios.items():
        ay = result['ay_sayisi']
        ay_str = f"{ay // 12} yıl {ay % 12} ay" if ay > 0 else "Hemen"
        
        comparison_data.append({
            "Senaryo": scenario_name,
            "Borç Kapatma Süresi": ay_str,
            "Toplam Faiz Maliyeti": format_tl(result['toplam_faiz']),
            "Simülasyon Sonu Birikim Değeri": format_tl(result['toplam_birikim'])
        })
        
        df = result['df'].copy()
        df['Senaryo'] = scenario_name
        final_df = pd.concat([final_df, df], ignore_index=True)

    st.dataframe(pd.DataFrame(comparison_data).sort_values(by="Borç Kapatma Süresi"), use_container_width=True, hide_index=True)

    # Görselleştirme
    create_comparison_chart(final_df)
    
    # Detaylı Tablo
    st.subheader("Aylık Detaylı Plan")
    st.dataframe(all_scenarios[list(all_scenarios.keys())[0]]['df'], use_container_width=True)

