# Gerekli kütüphaneleri içe aktarıyoruz. 'datetime' tarih işlemleri için.
import datetime

# --- VERİ MODELLERİ (SINIFLAR) ---
# Programda kullanacağımız her bir kavramı (Borç, Gelir vb.) bir nesne olarak tasarlıyoruz.

class Borc:
    """
    Her bir borcu temsil eden sınıf.
    """
    def __init__(self, ad, bakiye, faiz_orani, asgari_odeme, tur):
        self.ad = ad
        self.bakiye = float(bakiye)
        self.faiz_orani = float(faiz_orani)
        self.asgari_odeme = float(asgari_odeme)
        self.tur = tur # Örn: "Kredi Kartı", "Tüketici Kredisi"

    def __str__(self):
        # Bu nesneyi ekrana yazdırdığımızda nasıl görüneceğini belirler.
        return f"- {self.ad} ({self.tur}): {self.bakiye:.2f} TL (Faiz: %{self.faiz_orani}, Asgari: {self.asgari_odeme:.2f} TL)"

    def bakiye_arttir(self, tutar):
        """Kredi kartı gibi borçlara yeni harcama eklendiğinde bakiyeyi artırır."""
        self.bakiye += float(tutar)

class Gelir:
    """Kullanıcının gelir kaynaklarını temsil eden sınıf."""
    def __init__(self, ad, tutar, periyot="Aylık"):
        self.ad = ad
        self.tutar = float(tutar)
        self.periyot = periyot

    def __str__(self):
        return f"- {self.ad}: {self.tutar:.2f} TL ({self.periyot})"

class SabitGider:
    """Kira, abonelik gibi her ay sabit olan giderleri temsil eder."""
    def __init__(self, ad, tutar):
        self.ad = ad
        self.tutar = float(tutar)

    def __str__(self):
        return f"- {self.ad}: {self.tutar:.2f} TL"

class DegiskenGiderButcesi:
    """Mutfak, ulaşım gibi değişken gider kategorileri için ayrılan bütçeyi temsil eder."""
    def __init__(self, kategori_adi, aylik_butce):
        self.kategori_adi = kategori_adi
        self.aylik_butce = float(aylik_butce)
        self.harcanan_tutar = 0.0

    @property
    def kalan_butce(self):
        """Bu kategoride ne kadar bütçe kaldığını hesaplar."""
        return self.aylik_butce - self.harcanan_tutar

    def harcama_yap(self, tutar):
        """Bu kategoriye ait bir harcama yapıldığında çağrılır."""
        self.harcanan_tutar += float(tutar)

    def __str__(self):
        return f"- {self.kategori_adi}: Bütçe={self.aylik_butce:.2f} TL, Harcanan={self.harcanan_tutar:.2f} TL, Kalan={self.kalan_butce:.2f} TL"

# --- ANA YÖNETİCİ SINIFI ---
# Tüm verileri bir arada tutan ve işlemleri gerçekleştiren ana sınıf.

class FinansYoneticisi:
    def __init__(self):
        self.borclar = []
        self.gelirler = []
        self.sabit_giderler = []
        self.degisken_gider_butceleri = []
        # Örnek verilerle sistemi başlatabiliriz (test için)
        # self.borclar.append(Borc("X Bankası Kredi Kartı", 10000, 25.5, 1200, "Kredi Kartı"))
        # self.degisken_gider_butceleri.append(DegiskenGiderButcesi("Mutfak", 2000))

    def menu_goster(self):
        """Kullanıcıya sunulacak ana menüyü ekrana basar."""
        print("\n--- Borç Yönetim Programı Ana Menü ---")
        print("1. Yeni Borç Ekle")
        print("2. Yeni Harcama Ekle (En Önemli Kısım!)")
        print("3. Mevcut Borçları Görüntüle")
        print("4. Değişken Gider Bütçelerini Görüntüle")
        print("5. Gelir/Gider/Bütçe Ekle (Geliştirilecek)")
        print("6. Borç Ödeme Stratejisi Oluştur (Geliştirilecek)")
        print("0. Çıkış")
        return input("Seçiminiz: ")

    def borc_ekle(self):
        print("\n--- Yeni Borç Ekleme ---")
        ad = input("Borcun Adı (örn: Akbank Kredi Kartı): ")
        bakiye = input("Güncel Bakiye (örn: 5500.75): ")
        faiz_orani = input("Yıllık Faiz Oranı (%) (örn: 28.5): ")
        asgari_odeme = input("Aylık Asgari Ödeme Tutarı: ")
        tur = input("Borcun Türü (örn: Kredi Kartı, Tüketici Kredisi): ")
        yeni_borc = Borc(ad, bakiye, faiz_orani, asgari_odeme, tur)
        self.borclar.append(yeni_borc)
        print(f"'{ad}' adlı borç başarıyla eklendi.")

    def borclari_goster(self):
        print("\n--- Mevcut Borçlarınız ---")
        if not self.borclar:
            print("Henüz kayıtlı bir borcunuz bulunmuyor.")
            return
        for borc in self.borclar:
            print(borc)

    def degisken_gider_butcelerini_goster(self):
        print("\n--- Değişken Gider Bütçeleriniz ---")
        if not self.degisken_gider_butceleri:
            print("Henüz tanımlanmış bir değişken gider bütçeniz yok.")
            return
        for butce in self.degisken_gider_butceleri:
            print(butce)

    def harcama_ekle(self):
        """
        Kullanıcının günlük harcamalarını girmesini sağlar.
        Eğer harcama bir kredi kartı ile yapıldıysa, ilgili kartın borç bakiyesini otomatik günceller.
        """
        print("\n--- Yeni Harcama Ekleme ---")
        tutar = input("Harcama Tutarı: ")
        # Kategori seçimi
        if not self.degisken_gider_butceleri:
            print("Önce bir değişken gider bütçesi (örn: Mutfak, Ulaşım) tanımlamalısınız.")
            # Burada bütçe ekleme fonksiyonuna yönlendirme yapılabilir. Şimdilik geri dönüyoruz.
            return
        
        print("Harcama Kategorisi Seçin:")
        for i, butce in enumerate(self.degisken_gider_butceleri):
            print(f"{i + 1}. {butce.kategori_adi}")
        kategori_secim = int(input("Seçiminiz: ")) - 1
        secilen_kategori = self.degisken_gider_butceleri[kategori_secim]

        # Ödeme Yöntemi seçimi
        print("Ödeme Yöntemi Seçin:")
        print("1. Nakit / Banka Kartı")
        # Sistemdeki kredi kartlarını listele
        kredi_kartlari = [b for b in self.borclar if b.tur.lower() == "kredi kartı"]
        for i, kart in enumerate(kredi_kartlari):
            print(f"{i + 2}. {kart.ad}")
        
        yontem_secim = int(input("Seçiminiz: "))

        # Harcamayı ve borcu güncelleme
        secilen_kategori.harcama_yap(tutar)
        print(f"'{secilen_kategori.kategori_adi}' kategorisine {tutar} TL harcama eklendi.")

        if yontem_secim > 1:
            # Kullanıcı bir kredi kartı seçti
            secilen_kart_index = yontem_secim - 2
            secilen_kart = kredi_kartlari[secilen_kart_index]
            secilen_kart.bakiye_arttir(tutar)
            print(f"'{secilen_kart.ad}' bakiyesi güncellendi. Yeni Bakiye: {secilen_kart.bakiye:.2f} TL")

    def calistir(self):
        """Programın ana döngüsü. Kullanıcı çıkış yapana kadar çalışır."""
        while True:
            secim = self.menu_goster()
            if secim == '1':
                self.borc_ekle()
            elif secim == '2':
                self.harcama_ekle()
            elif secim == '3':
                self.borclari_goster()
            elif secim == '4':
                self.degisken_gider_butcelerini_goster()
            elif secim in ['5', '6']:
                print("Bu özellik sonraki adımlarda geliştirilecektir.")
            elif secim == '0':
                print("Programdan çıkılıyor...")
                break
            else:
                print("Geçersiz seçim. Lütfen tekrar deneyin.")

# --- PROGRAMI BAŞLATMA ---
if __name__ == "__main__":
    uygulama = FinansYoneticisi()
    # Programı kullanmadan önce en az bir tane değişken gider bütçesi eklememiz gerekiyor.
    # Bu kısmı daha sonra kullanıcı arayüzünden ekleteceğiz. Şimdilik manuel ekliyoruz.
    uygulama.degisken_gider_butceleri.append(DegiskenGiderButcesi("Mutfak", 2500))
    uygulama.degisken_gider_butceleri.append(DegiskenGiderButcesi("Ulaşım", 1000))

    uygulama.calistir()
