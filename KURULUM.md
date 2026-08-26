# Kurulum

Toplam süre: yaklaşık 1 saat. Alan adı dışında maliyeti yok.

---

## Adım 0 — Anonimlik için ayrı hesap

Mevcut GitHub hesabını kullanma. Repo sahibi profil sayfası herkese açıktır ve
kimliğini açığa çıkarır.

1. github.com/signup — yeni hesap, siteye özel e-posta ile
2. Ayarlardan **Settings → Emails → Keep my email addresses private** işaretle
3. Profil adı ve fotoğrafı boş bırak

Bu hesabın e-postası ileride sitenin iletişim adresi de olur.

---

## Adım 1 — NCBI API anahtarı

API anahtarı olmadan da çalışır ama saniyede 3 istekle sınırlanırsın ve tarama
yavaşlar. Ücretsiz.

1. ncbi.nlm.nih.gov/account — hesap aç
2. Sağ üstte kullanıcı adın → **Account settings**
3. **API Key Management** → **Create an API Key**
4. Çıkan anahtarı kopyala, bir sonraki adımda lazım

---

## Adım 2 — Repo

1. Yeni hesapla github.com/new
2. Repository name: `acil-literatur`
3. **Public** seç — özel repoda GitHub Actions dakikaları sınırlı, herkese açıkta sınırsız
4. Create repository

Sonra bu klasördeki dosyaları yükle. Terminalden:

```bash
cd acil-literatur
git init
git add .
git commit -m "İlk kurulum"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADIN/acil-literatur.git
git push -u origin main
```

Terminal kullanmak istemezsen GitHub arayüzünde **Add file → Upload files**
ile de yükleyebilirsin, ancak `.github` klasörü gizli olduğu için sürükle-bırak
ile yüklenmez; onu arayüzden `Create new file` diyip yol olarak
`.github/workflows/haftalik.yml` yazarak oluşturman gerekir.

---

## Adım 3 — API anahtarını repoya tanıt

1. Repo → **Settings → Secrets and variables → Actions**
2. **New repository secret**
3. Name: `NCBI_API_KEY`
4. Secret: Adım 1'deki anahtar
5. Add secret

Anahtar kod içine yazılmaz, loglarda görünmez.

---

## Adım 4 — GitHub Pages'i aç

1. Repo → **Settings → Pages**
2. **Source: GitHub Actions** seç (Deploy from a branch değil)
3. Kaydet

---

## Adım 5 — İlk çalıştırma

1. Repo → **Actions** sekmesi
2. Soldaki listeden **Haftalık tarama ve yayın**
3. Sağda **Run workflow** → **Run workflow**

2-3 dakika sürer. Yeşil tik görünce site yayında:
`https://KULLANICI_ADIN.github.io/acil-literatur/`

Kırmızı çarpı görürsen işe tıkla, hangi adımda durduğu yazar.

---

## Adım 6 — Alan adı (isteğe bağlı)

`acilliteratur.com` yıllık 10-15 dolar. Namecheap, Porkbun veya Cloudflare
Registrar kullanabilirsin.

1. Alan adını alırken **WHOIS gizliliğini** aç. Anonimlik için zorunlu.
2. Alan adı sağlayıcısında DNS kayıtları:

```
A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
CNAME www  KULLANICI_ADIN.github.io
```

3. Repo → Settings → Pages → **Custom domain** → `acilliteratur.com` → Save
4. **Enforce HTTPS** kutusunu işaretle (sertifika birkaç saatte hazır olur)

Yazım hatası için `aciliteratur.com` ve `acilliteratur.net` adreslerini de
alıp yönlendirmeyi düşünebilirsin.

---

## Yerelde deneme

Yayına almadan önce sonuçları görmek için:

```bash
pip install -r requirements.txt
export NCBI_API_KEY=anahtarin
python build.py --kuru
```

`--kuru` tarar, puanlar, o hafta hangi kayıtların seçileceğini terminale yazar
ama yayımlamaz. Her kaydın puanının nereden geldiğini de gösterir.

Siteyi tarayıcıda görmek için:

```bash
python build.py --sadece-uret
cd site && python -m http.server 8000
```

Sonra `localhost:8000` adresini aç.

---

## Ayar yapmak

Tek dosya: `config.yaml`. Kod değiştirmen gereken bir durum yok.

| İstediğin | Değiştir |
|---|---|
| Daha az/çok kayıt | `sayi.azami_kayit` |
| Daha seçici olsun | `sayi.esik` değerini yükselt |
| Yeni dergi ekle | `dergiler_a` veya `dergiler_b` |
| Yeni konu ekle | `mesh_oncelik` altına başlık ve MeSH terimleri |
| Yayın günü | `.github/workflows/haftalik.yml` içindeki cron |

MeSH terimi eklerken uydurma — doğrusunu
`ncbi.nlm.nih.gov/mesh` adresinden kontrol et. Yanlış terim sessizce
hiçbir şey eşleştirmez.

Değişiklikten sonra `python build.py --kuru` ile etkisine bak, sonra push et.

---

## Kılavuz sayfası

`data/kilavuzlar.yaml` elle güncellenir. Yeni kılavuz çıktığında:

1. Eskisini silme, adının sonuna `(önceki sürüm)` yaz
2. Yenisini üste ekle
3. Dosyanın başındaki `son_kontrol` tarihini güncelle
4. Push et — site kendiliğinden yenilenir

Ayda bir bakman yeterli. Yaş rozetleri yıldan otomatik hesaplanır.

---

## Kontrol listesi

Kurulumdan sonra bunları bir kez doğrula:

- [ ] Site açılıyor ve dört sayfa da çalışıyor
- [ ] Bir kaydın DOI linkine tıkla, doğru makaleye gidiyor mu
- [ ] Arşiv sayfasında arama ve konu filtresi çalışıyor mu
- [ ] Telefonda aç, okunabilir mi
- [ ] Alt bilgideki otomasyon bandı görünüyor mu
- [ ] Actions sekmesinde cron'un planlandığı görünüyor mu

---

## Sorun giderme

**Actions kırmızı çıkıyor, "PubMed esearch basarisiz"**
NCBI geçici olarak yanıt vermiyor olabilir. Run workflow ile tekrar dene.
Israrla sürerse `config.yaml`'daki dergi adlarında yazım hatası olabilir —
PubMed'de `"Dergi Adı"[Journal]` şeklinde elle aratıp kontrol et.

**Sayı boş çıktı**
Beklenen davranış olabilir. `python build.py --kuru` ile havuzda ne olduğuna
bak. Sürekli boş çıkıyorsa `sayi.esik` çok yüksek demektir.

**Cron çalışmadı**
GitHub cron'u yoğunlukta 10-60 dakika gecikir, bazen atlar. Ayrıca repo 60 gün
hiç güncellenmezse zamanlanmış işler durdurulur — bu sitede haftalık commit
olduğu için sorun olmaz.

**Site güncellenmiyor ama Actions yeşil**
Settings → Pages → Source'un **GitHub Actions** olduğunu doğrula.
