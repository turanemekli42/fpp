# Gerekli Kütüphaneleri İçe Aktarıyoruz
import streamlit as st
import sqlite3
import pandas as pd
import datetime
from dateutil.relativedelta import relativedelta
import copy
import os

# --- VERİTABANI İŞLEMLERİ ---
DB_FILE = "finans_veritabani.db"

def init_db():
    """Veritabanını Ve Tabloları Oluşturur."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS incomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, amount REAL, type TEXT,
            raises_per_year INTEGER, raise_percentage REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, balance REAL,
            interest_rate REAL, min_payment REAL, type TEXT,
            card_limit REAL DEFAULT 0, remaining_installments INTEGER DEFAULT 0, first_payment_date TEXT
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS fixed_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, amount REAL)")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS savings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, monthly_amount REAL, 
            strategy TEXT, percentage REAL
        )
    """)
    conn.commit()
    conn.close()

def load_data():
    """Veritabanından Tüm Verileri Yükler Ve Session State'e Aktarır."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    st.session_state.settings = {row['key']: row['value'] for row in cur.execute("SELECT * FROM settings").fetchall()}
    st.session_state.incomes = cur.execute("SELECT * FROM incomes").fetchall()
    st.session_state.debts = cur.execute("SELECT * FROM debts").fetchall()
    st.session_state.fixed_expenses = cur.execute("SELECT * FROM fixed_expenses").fetchall()
    st.session_state.savings = cur.execute("SELECT * FROM savings").fetchall()
    conn.close()

def save_record(table, data_dict):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    columns = ', '.join(data_dict.keys())
    placeholders = ', '.join(['?'] * len(data_dict))
    cur.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(data_dict.values()))
    conn.commit()
    conn.close()
    load_data()

def delete_record(table, record_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    load_data()

# --- SİMÜLASYON MOTORU ---
def calculate_payoff_plan_detailed(borclar_listesi, ekstra_odeme_gucu, gelirler_listesi, toplam_kredi_limiti):
    sim_borclar = [dict(b) for b in copy.deepcopy(borclar_listesi)]
    sim_gelirler = [dict(g) for g in copy.deepcopy(gelirler_listesi)]
    ay_sayaci, toplam_odenen_faiz = 0, 0.0
    grafik_verisi = {"Ay": [0], "Toplam Borç": [sum(b['balance'] for b in sim_borclar)]}
    tablo_sutunlari = ['Ay', 'Tarih'] + [b['name'] for b in borclar_listesi] + ['Toplam Kalan Borç']
    tablo_verisi = []
    
    while any(b['balance'] > 0 for b in sim_borclar) and ay_sayaci < 600:
        ay_sayaci += 1
        current_date = datetime.date.today() + relativedelta(months=ay_sayaci)
        aylik_gelir_artis = 0
        for gelir in sim_gelirler:
            if gelir['type'] == 'Maaş (Düzenli Ve Zamlı)':
                if (gelir['raises_per_year'] == 1 and (ay_sayaci - 1) % 12 == 0 and ay_sayaci > 1) or \
                   (gelir['raises_per_year'] == 2 and (ay_sayaci - 1) % 6 == 0 and ay_sayaci > 1):
                    artis = gelir['amount'] * (gelir['raise_percentage'] / 100)
                    gelir['amount'] += artis
                    aylik_gelir_artis += artis
        ekstra_odeme_gucu += aylik_gelir_artis
        
        kartopu_etkisi = 0
        for borc in sim_borclar:
            if borc['balance'] > 0:
                is_active_installment = borc['type'] == 'Sabit Taksitli Borç (Okul, Senet Vb.)' and borc['first_payment_date'] and current_date >= datetime.datetime.strptime(borc['first_payment_date'], '%Y-%m-%d').date()
                if borc['type'] != 'Sabit Taksitli Borç (Okul, Senet Vb.)' or is_active_installment:
                    if borc['type'] != 'Sabit Taksitli Borç (Okul, Senet Vb.)':
                        aylik_faiz = borc['balance'] * (borc['interest_rate'] / 100 / 12)
                        borc['balance'] += aylik_faiz
                        toplam_odenen_faiz += aylik_faiz
                        if borc['type'] == 'KMH / Ek Hesap': borc['min_payment'] = aylik_faiz
                        elif borc['type'] == 'Kredi Kartı': borc['min_payment'] = borc['balance'] * (0.40 if toplam_kredi_limiti > 50000 else 0.20)

        odeme_gucu = ekstra_odeme_gucu
        kalan_borclar_sirali = [b for b in borclar_listesi if dict(next((sim_b for sim_b in sim_borclar if sim_b['id'] == b['id']), None))['balance'] > 0]
        hedef_borc = kalan_borclar_sirali[0] if kalan_borclar_sirali else None

        for borc in sim_borclar:
            if borc['balance'] > 0:
                is_active_installment_payment = borc['type'] == 'Sabit Taksitli Borç (Okul, Senet Vb.)' and borc['first_payment_date'] and current_date >= datetime.datetime.strptime(borc['first_payment_date'], '%Y-%m-%d').date() and borc['remaining_installments'] > 0
                if borc['type'] != 'Sabit Taksitli Borç (Okul, Senet Vb.)' or is_active_installment_payment:
                    odenecek_asgari_orjinal = borc['min_payment']
                    if hedef_borc and borc['id'] == hedef_borc['id']:
                        odeme = min(borc['balance'], borc['min_payment'] + odeme_gucu)
                    else:
                        odeme = min(borc['balance'], borc['min_payment'])
                    borc['balance'] -= odeme
                    if borc['type'] == 'Sabit Taksitli Borç (Okul, Senet Vb.)' and borc['balance'] > 0: borc['remaining_installments'] -= 1
                    if borc['balance'] <= 0: kartopu_etkisi += odenecek_asgari_orjinal

        ekstra_odeme_gucu += kartopu_etkisi
        
        toplam_kalan_borc = sum(b['balance'] for b in sim_borclar if b['balance'] > 0)
        grafik_verisi["Ay"].append(ay_sayaci); grafik_verisi["Toplam Borç"].append(toplam_kalan_borc)
        aylik_veri_satiri = [ay_sayaci, current_date.strftime("%B %Y")]
        for b_orj in borclar_listesi:
            ilgili_borc = next((sim_b for sim_b in sim_borclar if sim_b['id'] == b_orj['id']), None)
            if ilgili_borc and ilgili_borc['balance'] > 0:
                aylik_veri_satiri.append(f"{ilgili_borc['balance']:,.2f} TL")
            else: aylik_veri_satiri.append("✅ BİTTİ")
        aylik_veri_satiri.append(f"{toplam_kalan_borc:,.2f} TL")
        tablo_verisi.append(aylik_veri_satiri)

    if ay_sayaci >= 600: return None
    grafik_df = pd.DataFrame(grafik_verisi).set_index("Ay")
    tablo_df = pd.DataFrame(tablo_verisi, columns=tablo_sutunlari)
    return ay_sayaci, toplam_odenen_faiz, grafik_df, tablo_df

# --- STREAMLIT ARAYÜZÜ ---
st.set_page_config(page_title="Finans Yönetim Paneli", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style> h1, h2, h3 { text-transform: capitalize; } .stButton>button { border-radius: 20px; border: 1px solid #E0E0E0; } </style>""", unsafe_allow_html=True)
st.title("💸 Kişisel Finans Ve Borç Yönetim Asistanı")

if 'initialized' not in st.session_state:
    if not os.path.exists(DB_FILE): init_db()
    load_data()
    st.session_state.initialized = True

tabs = st.tabs(["ℹ️ Başlarken & Yardım", "📊 Genel Durum", "➕ Yeni Kayıt Ekle", "🚀 Strateji Ve Simülasyon"])

with tabs[0]:
    st.header("Programa Hoş Geldiniz!")
    st.markdown("""
        Bu Uygulama, Finansal Durumunuzu Kontrol Altına Almanıza, Borçlarınızı Stratejik Olarak Daha Hızlı Bitirmenize Ve Birikim Hedeflerinize Ulaşmanıza Yardımcı Olmak İçin Tasarlanmıştır.
        
        ### Programın Amacı Nedir?
        - **Netlik Kazanmak:** Tüm Gelir, Gider Ve Borçlarınızı Tek Bir Yerde Görerek Finansal Fotoğrafınızı Netleştirin.
        - **Strateji Oluşturmak:** 'Çığ' Ve 'Kartopu' Gibi Kanıtlanmış Yöntemlerle, Borçlarınızı En Verimli Şekilde Nasıl Kapatacağınızı Keşfedin.
        - **Geleceği Planlamak:** Simülasyon Motoru Sayesinde, Seçtiğiniz Planla Borçlarınızın Ne Zaman Biteceğini, Ne Kadar Faizden Tasarruf Edeceğinizi Görün Ve Motive Olun.

        ### Adım Adım Kullanım Kılavuzu
        1.  **Adım: Finansal Verilerinizi Girin (Önemli!)**
            - **`Yeni Kayıt Ekle`** Sekmesine Gidin.
            - **Tüm Gelirlerinizi** Ekleyin. Eğer Maaş Gibi Düzenli Bir Geliriniz Varsa, "Maaş" Seçeneğini İşaretleyip Olası Yıllık Zam Oranlarınızı Girerek Simülasyonu Çok Daha Gerçekçi Hale Getirebilirsiniz.
            - **Tüm Borçlarınızı** Ekleyin. "Kredi Kartı" Eklerken Kart Limitinizi Girmeniz Yeterlidir. "KMH" Veya "Sabit Taksitli Borç" Eklerken İlgili Alanları Doldurun. Program Gerekli Hesaplamaları Otomatik Yapar.
            - **Sabit Giderlerinizi** (Kira, Abonelikler Vb.) Ve Aylık **Birikim Hedeflerinizi** Ekleyin. Birikim İçin Sabit Bir Tutar Veya Kalan Paranın Yüzdesi Şeklinde İki Farklı Strateji Seçebilirsiniz.

        2.  **Adım: Genel Durumunuzu Gözden Geçirin**
            - **`Genel Durum`** Sekmesine Tıklayın. Eklediğiniz Her Kaydın Yanında Bir "Sil" Butonu Bulunur.
            - Eklediğiniz Tüm Bilgilerin Modern Bir Kart Tasarımıyla Özetlendiğini Göreceksiniz. Bu Sizin Mevcut Finansal Fotoğrafınızdır.

        3.  **Adım: Stratejinizi Oluşturun Ve Geleceği Görün**
            - **`Strateji Ve Simülasyon`** Sekmesine Gidin.
            - Program, Girdiğiniz Verilere Göre Elinizde Kalan "Net Fazlayı" Ve Bu Fazlanın Birikim/Borç Ödemesi Arasında Nasıl Dağıtıldığını Gösterir.
            - "Çığ" Veya "Kartopu" Yöntemlerinden Birini Seçin Ve **"Simülasyonu Çalıştır"** Butonuna Basın.
            - **Sonuçları İnceleyin:** Borçlarınızın Ne Zaman Biteceğini, Toplam Ne Kadar Faiz Ödeyeceğinizi, Borcunuzun Zamanla Azalışını Gösteren Grafiği Ve Ay Ay Tüm Detayları İçeren Tabloyu Görerek Geleceğinizi Planlayın!
    """)

with tabs[1]:
    st.header("Finansal Gösterge Paneli")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("💰 Gelirler")
            if not st.session_state.incomes: st.info("Gelir Eklenmemiş.")
            for income in st.session_state.incomes:
                st.markdown(f"**{income['name']}:** `{income['amount']:,.2f} TL`")
                if st.button(f"Sil##gelir{income['id']}", key=f"del_gelir_{income['id']}"): delete_record("incomes", income['id']); st.rerun()
    with col2:
        with st.container(border=True):
            st.subheader("🎯 Birikim Hedefleri")
            if not st.session_state.savings: st.info("Birikim Hedefi Eklenmemiş.")
            for saving in st.session_state.savings:
                st.markdown(f"**{saving['name']}:** `{saving['monthly_amount']:,.2f} TL/ay ({saving['strategy']})`")
                if st.button(f"Sil##birikim{saving['id']}", key=f"del_birikim_{saving['id']}"): delete_record("savings", saving['id']); st.rerun()
    
    st.subheader("💳 Toplam Borç Durumu")
    if not st.session_state.debts: st.info("Borç Eklenmemiş.")
    else:
        toplam_borc = sum(d['balance'] for d in st.session_state.debts)
        toplam_kredi_karti_limiti = sum(d['card_limit'] for d in st.session_state.debts if d['type'] == 'Kredi Kartı')
        c1, c2 = st.columns(2)
        c1.metric("Toplam Borç Bakiyesi", f"{toplam_borc:,.2f} TL")
        c2.metric("Hesaplanan Toplam Kredi Kartı Limiti", f"{toplam_kredi_karti_limiti:,.2f} TL")

    st.subheader("Borç Detayları")
    for debt in st.session_state.debts:
        with st.container(border=True):
            col_b1, col_b2 = st.columns([4, 1])
            with col_b1:
                if debt['type'] == 'Sabit Taksitli Borç (Okul, Senet Vb.)':
                    st.markdown(f"**{debt['name']} ({debt['type']}):** `{debt['balance']:,.2f} TL` (Kalan Taksit: *{debt['remaining_installments']}*)")
                else:
                    st.markdown(f"**{debt['name']} ({debt['type']}):** `{debt['balance']:,.2f} TL` (Faiz: *%{debt['interest_rate']}*)")
            with col_b2:
                if st.button(f"Sil##borc{debt['id']}", key=f"del_borc_{debt['id']}"): delete_record("debts", debt['id']); st.rerun()
    
    with st.container(border=True):
        st.subheader("🏠 Sabit Giderler")
        if not st.session_state.fixed_expenses: st.info("Sabit Gider Eklenmemiş.")
        for expense in st.session_state.fixed_expenses:
            st.markdown(f"**{expense['name']}:** `{expense['amount']:,.2f} TL`")
            if st.button(f"Sil##gider{expense['id']}", key=f"del_gider_{expense['id']}"): delete_record("fixed_expenses", expense['id']); st.rerun()

with tabs[2]:
    st.header("Veri Giriş Formları")
    with st.expander("Yeni Gelir Ekle", expanded=True):
        gelir_tipi_secim = st.selectbox("Eklenecek Gelirin Türünü Seçin", ["Maaş (Düzenli Ve Zamlı)", "Diğer Düzenli Gelir (Kira, Ek İş Vb. - Zamsız)", "Tek Seferlik Gelir (Miras, İkramiye Vb.)"], key="gelir_tur_secimi")
        with st.form(f"gelir_form_{gelir_tipi_secim}", clear_on_submit=True):
            st.write(f"**{gelir_tipi_secim} Bilgilerini Girin**")
            gelir_ad = st.text_input("Gelir Kaynağının Adı (Örn: Maaş)")
            gelir_tutar = st.number_input("Tutar", min_value=0.01, format="%.2f")
            zam_sayisi, zam_orani = 0, 0.0
            if gelir_tipi_secim == "Maaş (Düzenli Ve Zamlı)":
                zam_sayisi = st.selectbox("Yılda Kaç Kez Zam Bekleniyor?", [0, 1, 2], index=1)
                zam_orani = st.number_input("Tahmini Yıllık Zam Oranı (%)", min_value=0.0, max_value=200.0, value=40.0, format="%.1f")
            if st.form_submit_button("Geliri Kaydet"):
                save_record("incomes", {"name": gelir_ad, "amount": gelir_tutar, "type": gelir_tipi_secim, "raises_per_year": zam_sayisi, "raise_percentage": zam_orani}); st.success(f"'{gelir_ad}' Eklendi!")
    with st.expander("Yeni Borç Ekle"):
        borc_tur_secim = st.selectbox("Eklenecek Borcun Türünü Seçin", ["Kredi Kartı", "Tüketici Kredisi", "Konut Kredisi", "KMH / Ek Hesap", "Sabit Taksitli Borç (Okul, Senet Vb.)", "Diğer"], key="borc_tur_secimi")
        with st.form(f"borc_form_{borc_tur_secim}", clear_on_submit=True):
            st.write(f"**{borc_tur_secim} Bilgilerini Girin**")
            borc_ad = st.text_input("Borcun Adı")
            borc_bakiye, borc_faiz, asgari_odeme, kart_limiti, taksit_sayisi, ilk_odeme = 0.0, 0.0, 0.0, 0.0, 0, None
            if borc_tur_secim == "Sabit Taksitli Borç (Okul, Senet Vb.)":
                asgari_odeme = st.number_input("Aylık Taksit Tutarı", min_value=0.01, format="%.2f")
                taksit_sayisi = st.number_input("Kalan Taksit Sayısı", min_value=1, step=1)
                ilk_odeme = st.date_input("İlk Ödeme Tarihi", value=datetime.date.today() + relativedelta(months=1))
                borc_faiz = 0.0
            else:
                borc_bakiye = st.number_input("Güncel Bakiye", min_value=0.01, format="%.2f")
                borc_faiz = st.number_input("Yıllık Faiz Oranı (%)", min_value=0.01, format="%.2f")
                if borc_tur_secim == "Kredi Kartı": kart_limiti = st.number_input("Kart Limiti", min_value=0.01, help="Bu karta ait bireysel limiti giriniz.")
                elif borc_tur_secim not in ["KMH / Ek Hesap"]: asgari_odeme = st.number_input("Aylık Asgari Ödeme", min_value=0.01, format="%.2f")
            if st.form_submit_button("Borcu Kaydet"):
                kaydedilecek_bakiye = asgari_odeme * taksit_sayisi if borc_tur_secim == "Sabit Taksitli Borç (Okul, Senet Vb.)" else borc_bakiye
                save_record("debts", {"name": borc_ad, "balance": kaydedilecek_bakiye, "interest_rate": borc_faiz, "min_payment": asgari_odeme, "type": borc_tur_secim, "card_limit": kart_limiti, "remaining_installments": taksit_sayisi, "first_payment_date": str(ilk_odeme)}); st.success(f"'{borc_ad}' Başarıyla Eklendi!")
    with st.expander("Yeni Sabit Gider Ekle"):
        with st.form("sabit_gider_formu", clear_on_submit=True):
            gider_ad = st.text_input("Giderin Adı"); gider_tutar = st.number_input("Aylık Tutar", min_value=0.01, format="%.2f")
            if st.form_submit_button("Sabit Gideri Kaydet"): save_record("fixed_expenses", {"name": gider_ad, "amount": gider_tutar}); st.success(f"'{gider_ad}' Eklendi!")
    with st.expander("Yeni Birikim Hedefi Ekle"):
        with st.form("birikim_formu", clear_on_submit=True):
            birikim_ad = st.text_input("Birikim Hedefinin Adı")
            birikim_stratejisi = st.selectbox("Birikim Stratejisi", ["Sabit Tutar", "Yüzdesel Paylaşım"])
            birikim_tutar, birikim_yuzde = 0.0, 0.0
            if birikim_stratejisi == "Sabit Tutar": birikim_tutar = st.number_input("Aylık Ayrılacak Sabit Tutar", min_value=0.01, format="%.2f")
            else: birikim_yuzde = st.slider("Kalan Paranın Yüzde Kaçı Birikime Aktarılsın?", 0, 100, 90)
            if st.form_submit_button("Birikim Hedefini Kaydet"): save_record("savings", {"name": birikim_ad, "monthly_amount": birikim_tutar, "strategy": birikim_stratejisi, "percentage": birikim_yuzde}); st.success(f"'{birikim_ad}' Hedefi Eklendi!")

with tabs[3]:
    st.header("Strateji Geliştirme Ve Simülasyon")
    if not st.session_state.incomes or not st.session_state.debts:
        st.warning("Simülasyonu Çalıştırmak İçin En Az Bir Gelir Ve Bir Borç Eklemelisiniz.")
    else:
        toplam_kredi_limiti = sum(b['card_limit'] for b in st.session_state.debts if b['type'] == 'Kredi Kartı')
        toplam_gelir = sum(g['amount'] for g in st.session_state.incomes if g['type'] != 'Tek Seferlik Gelir') + sum(g['amount'] for g in st.session_state.incomes if g['type'] == 'Tek Seferlik Gelir')
        toplam_sabit_giderler = sum(g['amount'] for g in st.session_state.fixed_expenses)
        borc_asgari_odemeleri = 0
        for borc in st.session_state.debts:
            if borc['type'] == 'Kredi Kartı': borc_asgari_odemeleri += borc['balance'] * (0.40 if toplam_kredi_limiti > 50000 else 0.20)
            elif borc['type'] == 'KMH / Ek Hesap': borc_asgari_odemeleri += borc['balance'] * (borc['interest_rate'] / 100 / 12)
            else: borc_asgari_odemeleri += borc['min_payment']
        toplam_zorunlu_cikis = borc_asgari_odemeleri + toplam_sabit_giderler
        net_kullanilabilir_fazla = toplam_gelir - toplam_zorunlu_cikis
        
        aylik_birikim_payi, borclar_icin_ekstra_guc = 0, 0
        saving_goal = st.session_state.savings[0] if st.session_state.savings else None
        if saving_goal:
            if saving_goal['strategy'] == 'Sabit Tutar':
                aylik_birikim_payi = saving_goal['monthly_amount']
            else:
                if net_kullanilabilir_fazla > 0: aylik_birikim_payi = net_kullanilabilir_fazla * (saving_goal['percentage'] / 100)
        borclar_icin_ekstra_guc = net_kullanilabilir_fazla - aylik_birikim_payi
        
        st.subheader("Nakit Akışı Analizi")
        col1, col2, col3 = st.columns(3); col1.metric("✅ Toplam Aylık Gelir", f"{toplam_gelir:,.2f} TL"); col2.metric("❌ Zorunlu Giderler (Borç Asgarileri + Sabit Giderler)", f"{toplam_zorunlu_cikis:,.2f} TL"); col3.metric("💰 Net Kullanılabilir Fazla", f"{net_kullanilabilir_fazla:,.2f} TL")
        if saving_goal:
            st.success(f"Bu Fazla Tutarın Dağılımı ({saving_goal['strategy']}):")
            col_s1, col_s2 = st.columns(2); col_s1.metric("🎯 Birikime Aktarılacak", f"{aylik_birikim_payi:,.2f} TL"); col_s2.metric("⚡️ Borç Ödemesine Aktarılacak (Ekstra Güç)", f"{borclar_icin_ekstra_guc:,.2f} TL")
        st.divider()
        
        if borclar_icin_ekstra_guc > 0:
            st.subheader("Borç Ödeme Stratejisi Ve Simülasyon")
            secilen_strateji = st.radio("Stratejinizi Seçin:", ("Çığ Yöntemi (En Hızlı Ve En Tasarruflu)", "Kartopu Yöntemi (En Motive Edici)"))
            if st.button("📈 Simülasyonu Çalıştır Ve Ödeme Planını Gör"):
                if secilen_strateji.startswith("Çığ"): sirali_borclar = sorted(st.session_state.debts, key=lambda b: b['interest_rate'], reverse=True)
                else: sirali_borclar = sorted(st.session_state.debts, key=lambda b: b['balance'])
                sonuc = calculate_payoff_plan_detailed(sirali_borclar, borclar_icin_ekstra_guc, st.session_state.incomes, toplam_kredi_limiti)
                if sonuc is None: st.error("Plan 50 Yıldan Uzun Sürüyor. Lütfen Verilerinizi Gözden Geçirin.")
                else:
                    ay_sayaci, toplam_faiz, grafik_df, tablo_df = sonuc
                    toplam_yil, kalan_ay = divmod(ay_sayaci, 12)
                    st.success(f"Tebrikler! Bu Plana Sadık Kalırsanız, Tüm Borçlarınız **{toplam_yil} Yıl {kalan_ay} Ay** Sonra Bitecek.")
                    st.metric("Bu Süreçte Ödeyeceğiniz Toplam Faiz", f"{toplam_faiz:,.2f} TL")
                    st.subheader("Toplam Borcun Zamanla Azalması"); st.line_chart(grafik_df)
                    st.subheader("Ay Ay Detaylı Ödeme Tablosu"); st.dataframe(tablo_df, use_container_width=True)
        else:
            st.error(f"Bütçenizde **{borclar_icin_ekstra_guc:,.2f} TL** Açık Var Veya Borçları Hızlandırmak İçin Ekstra Gücünüz Kalmadı. Simülasyon Çalıştırılamıyor.")
