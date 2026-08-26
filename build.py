#!/usr/bin/env python3
"""
Acil Literatur — otomatik haftalik literatur seckisi.

Calisma sirasi:
  1. PubMed'den dergi listesine gore kayit ceker (esearch + efetch)
  2. Yayin tipi ve MeSH terimlerine gore deterministik puan verir
  3. Havuza ekler, suresi dolanlari duser
  4. Kurallara gore o haftanin sayisini secer
  5. Statik HTML uretir

Uretilen hicbir cumle yoktur. Tum alanlar PubMed kaydindan birebir alinir.

Kullanim:
  python build.py            normal calisma
  python build.py --kuru     tarama yapar, yayimlamaz (deneme icin)
  python build.py --sadece-uret  tarama yapmadan mevcut havuzdan site uretir
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

KOK = Path(__file__).parent
VERI = KOK / "data"
CIKTI = KOK / "site"
HAVUZ_YOLU = VERI / "havuz.json"
SAYILAR_YOLU = VERI / "sayilar.json"

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.environ.get("NCBI_API_KEY", "")

AYLAR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
    7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
}


# ---------------------------------------------------------------- yardimcilar

def log(mesaj):
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {mesaj}", flush=True)


def tr_tarih(iso):
    """2026-08-28 -> 28 Ağustos 2026"""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
    except (ValueError, TypeError):
        return iso or ""
    return f"{d.day} {AYLAR[d.month]} {d.year}"


def yapilandirma_yukle():
    with open(KOK / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def json_yukle(yol, varsayilan):
    if not yol.exists():
        return varsayilan
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def json_yaz(yol, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)


def istek(url, deneme=3):
    """Basit yeniden deneme. Basarisiz olursa None doner — sessiz gecmez."""
    for i in range(deneme):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            log(f"  istek hatasi ({i + 1}/{deneme}): {e}")
            time.sleep(3 * (i + 1))
    return None


# ------------------------------------------------------------------- pubmed

def sorgu_kur(cfg):
    """Dergi listesi + tarih penceresinden PubMed sorgusu uretir."""
    dergiler = cfg["dergiler_a"] + cfg["dergiler_b"]
    dergi_bloku = " OR ".join(f'"{d}"[Journal]' for d in dergiler)
    bugun = datetime.now(timezone.utc).date()
    basla = bugun - timedelta(days=cfg["tarama"]["gun_penceresi"])
    tarih = f'("{basla:%Y/%m/%d}"[EDAT] : "{bugun:%Y/%m/%d}"[EDAT])'
    return f"({dergi_bloku}) AND {tarih}"


def pmid_ara(sorgu, azami):
    url = f"{EUTILS}/esearch.fcgi?" + urllib.parse.urlencode({
        "db": "pubmed", "term": sorgu, "retmax": azami,
        "retmode": "json", "sort": "date", **({"api_key": API_KEY} if API_KEY else {}),
    })
    ham = istek(url)
    if ham is None:
        raise RuntimeError("PubMed esearch basarisiz")
    return json.loads(ham)["esearchresult"].get("idlist", [])


def _metin(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def kayit_ayikla(makale):
    """PubmedArticle XML -> sozluk. Bulunamayan alan bos birakilir, tahmin edilmez."""
    mc = makale.find("MedlineCitation")
    art = mc.find("Article")

    pmid = _metin(mc.find("PMID"))
    baslik = _metin(art.find("ArticleTitle"))

    dergi_el = art.find("Journal")
    dergi = _metin(dergi_el.find("ISOAbbreviation")) if dergi_el is not None else ""
    if not dergi and dergi_el is not None:
        dergi = _metin(dergi_el.find("Title"))

    doi = ""
    for eid in art.findall(".//ELocationID"):
        if eid.get("EIdType") == "doi":
            doi = _metin(eid)
            break
    if not doi:
        for aid in makale.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = _metin(aid)
                break

    tipler = [_metin(t) for t in art.findall(".//PublicationType")]
    mesh = [_metin(d) for d in mc.findall(".//MeshHeading/DescriptorName")]

    yil = ay = gun = ""
    for yol in ("Journal/JournalIssue/PubDate", "ArticleDate"):
        pd = art.find(yol)
        if pd is not None:
            yil = _metin(pd.find("Year")) or yil
            ay = _metin(pd.find("Month")) or ay
            gun = _metin(pd.find("Day")) or gun
            if yil:
                break

    return {
        "pmid": pmid,
        "baslik": baslik,
        "dergi": dergi,
        "doi": doi,
        "tipler": tipler,
        "mesh": mesh,
        "yil": yil,
        "ay": ay,
        "gun": gun,
    }


def kayitlari_cek(pmidler):
    kayitlar = []
    for i in range(0, len(pmidler), 100):
        grup = pmidler[i:i + 100]
        url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode({
            "db": "pubmed", "id": ",".join(grup), "retmode": "xml",
            **({"api_key": API_KEY} if API_KEY else {}),
        })
        ham = istek(url)
        if ham is None:
            raise RuntimeError("PubMed efetch basarisiz")
        kok = ET.fromstring(ham)
        for makale in kok.findall(".//PubmedArticle"):
            kayitlar.append(kayit_ayikla(makale))
        log(f"  {min(i + 100, len(pmidler))}/{len(pmidler)} kayit alindi")
        time.sleep(0.4 if API_KEY else 1.0)
    return kayitlar


# ----------------------------------------------------------------- puanlama

def puanla(kayit, cfg):
    """
    Deterministik puanlama. Ayni girdi her zaman ayni cikti.
    Doner: (puan, konu_etiketleri) — dislanan kayitlar icin (None, []).
    """
    p = cfg["puanlama"]

    if any(t in p["dislanan_tipler"] for t in kayit["tipler"]):
        return None, []

    puan = 0
    gerekce = []

    tip_puanlari = [(t, p["yayin_tipi"][t]) for t in kayit["tipler"] if t in p["yayin_tipi"]]
    if tip_puanlari:
        # Ana tip: en yuksek puanli olan. Multicenter gibi ekler ayrica sayilir.
        ana = max(tip_puanlari, key=lambda x: x[1])
        puan += ana[1]
        gerekce.append(f"{ana[0]} +{ana[1]}")
        for t, v in tip_puanlari:
            if t in ("Multicenter Study", "Observational Study") and t != ana[0]:
                puan += v
                gerekce.append(f"{t} +{v}")

    if kayit["dergi"] in cfg["dergiler_a"]:
        puan += p["dergi_a"]
        gerekce.append(f"A dergisi +{p['dergi_a']}")
    elif kayit["dergi"] in cfg["dergiler_b"]:
        puan += p["dergi_b"]
        gerekce.append(f"B dergisi +{p['dergi_b']}")

    mesh_kumesi = set(kayit["mesh"])
    konular = [ad for ad, terimler in cfg["mesh_oncelik"].items()
               if mesh_kumesi & set(terimler)]
    if konular:
        puan += p["mesh_oncelik"]
        gerekce.append(f"öncelikli konu +{p['mesh_oncelik']}")

    kayit["gerekce"] = gerekce
    return puan, konular


KILAVUZ_TIPLERI = ("Guideline", "Practice Guideline",
                  "Consensus Development Conference")


def kategori_bul(puan, cfg, tipler=()):
    """Kilavuzlar siralamayi atlar: her zaman en ust kategoriye girer."""
    if any(t in KILAVUZ_TIPLERI for t in tipler):
        return cfg["kategoriler"][0]
    for k in cfg["kategoriler"]:
        if puan >= k["asgari_puan"]:
            return k
    return None


# -------------------------------------------------------------------- havuz

def havuzu_guncelle(havuz, kayitlar, cfg, bugun):
    yeni = 0
    for k in kayitlar:
        if k["pmid"] in havuz:
            continue
        puan, konular = puanla(k, cfg)
        if puan is None or puan < cfg["sayi"]["esik"]:
            continue
        k.update({
            "puan": puan,
            "konular": konular,
            "eklendi": bugun.isoformat(),
            "sayi": None,
        })
        havuz[k["pmid"]] = k
        yeni += 1
    return yeni


def havuzu_temizle(havuz, cfg, bugun):
    sinir = bugun - timedelta(weeks=cfg["havuz"]["azami_hafta"])
    dusen = [p for p, k in havuz.items()
             if k["sayi"] is None
             and datetime.fromisoformat(k["eklendi"]).date() < sinir]
    for p in dusen:
        del havuz[p]
    return len(dusen)


def sayiyi_sec(havuz, cfg):
    """
    Secim kurallari:
      - Esigin altindakiler zaten havuza girmedi
      - Kilavuzlar siralamayi atlar, dogrudan girer
      - Ayni konudan en fazla N kayit
      - Esitlikte: kilavuz > RCT > meta > gozlemsel, sonra havuzda bekleyen once
    """
    adaylar = [k for k in havuz.values() if k["sayi"] is None]
    if not adaylar:
        return []

    tip_sirasi = {"Guideline": 0, "Practice Guideline": 0,
                  "Consensus Development Conference": 0,
                  "Randomized Controlled Trial": 1,
                  "Meta-Analysis": 2, "Systematic Review": 2}

    def sira_anahtari(k):
        oncelik = min([tip_sirasi.get(t, 3) for t in k["tipler"]] or [3])
        return (-k["puan"], oncelik, k["eklendi"])

    adaylar.sort(key=sira_anahtari)

    secilen, konu_sayaci = [], {}
    kilavuzlar = [k for k in adaylar
                  if any(t in tip_sirasi and tip_sirasi[t] == 0 for t in k["tipler"])]

    for k in kilavuzlar:
        if len(secilen) >= cfg["sayi"]["azami_kayit"]:
            break
        secilen.append(k)
        for konu in k["konular"]:
            konu_sayaci[konu] = konu_sayaci.get(konu, 0) + 1

    for k in adaylar:
        if len(secilen) >= cfg["sayi"]["azami_kayit"]:
            break
        if k in secilen:
            continue
        if any(konu_sayaci.get(c, 0) >= cfg["sayi"]["konu_basina_azami"] for c in k["konular"]):
            continue
        secilen.append(k)
        for konu in k["konular"]:
            konu_sayaci[konu] = konu_sayaci.get(konu, 0) + 1

    return secilen


# ------------------------------------------------------------------- uretim

def zenginlestir(k, cfg):
    kat = kategori_bul(k["puan"], cfg, k.get("tipler", []))
    k = dict(k)
    k["kategori_ad"] = kat["ad"] if kat else ""
    k["kategori_kod"] = kat["kod"] if kat else ""
    ana = [t for t in k["tipler"] if t in cfg["puanlama"]["yayin_tipi"]]
    k["tip_etiketi"] = ana[0] if ana else ""
    parcalar = [p for p in (k.get("ay"), k.get("yil")) if p]
    k["tarih_etiketi"] = " ".join(parcalar)
    return k


def siteyi_uret(cfg, sayilar, havuz, durum):
    env = Environment(
        loader=FileSystemLoader(KOK / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    CIKTI.mkdir(exist_ok=True)

    with open(VERI / "kilavuzlar.yaml", encoding="utf-8") as f:
        kilavuzlar = yaml.safe_load(f)

    bu_yil = datetime.now(timezone.utc).year
    for konu in kilavuzlar["konular"]:
        for kayit in konu["kayitlar"]:
            yas = bu_yil - kayit["yil"]
            kayit["yas"] = yas
            kayit["yas_kod"] = ("yeni" if yas < 2 else "orta" if yas < 5
                                else "eski" if yas < 10 else "cok_eski")

    sirali = sorted(sayilar, key=lambda s: s["tarih"], reverse=True)
    for s in sirali:
        s["tarih_tr"] = tr_tarih(s["tarih"])
        s["kayitlar"] = [zenginlestir(k, cfg) for k in s["kayitlar"]]

    tum_kayitlar = [k for s in sirali for k in s["kayitlar"]]
    konu_sayaci = {}
    for k in tum_kayitlar:
        for c in k.get("konular", []):
            konu_sayaci[c] = konu_sayaci.get(c, 0) + 1

    ortak = {
        "site": cfg["site"],
        "durum": durum,
        "uretim_tarihi": tr_tarih(datetime.now(timezone.utc).date().isoformat()),
    }

    sayfalar = {
        "index.html": ("index.html", {"sayi": sirali[0] if sirali else None}),
        "arsiv.html": ("arsiv.html", {
            "sayilar": sirali,
            "konular": sorted(konu_sayaci.items(), key=lambda x: -x[1]),
            "toplam": len(tum_kayitlar),
        }),
        "kilavuzlar.html": ("kilavuzlar.html", {"kilavuzlar": kilavuzlar}),
        "yontem.html": ("yontem.html", {"cfg": cfg}),
    }

    for dosya, (sablon, baglam) in sayfalar.items():
        html = env.get_template(sablon).render(**ortak, **baglam)
        (CIKTI / dosya).write_text(html, encoding="utf-8")
        log(f"  {dosya} yazildi")

    import shutil
    shutil.copy(KOK / "static" / "style.css", CIKTI / "style.css")
    (CIKTI / ".nojekyll").write_text("")

    json_yaz(CIKTI / "kayitlar.json", tum_kayitlar)


# --------------------------------------------------------------------- akis

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kuru", action="store_true", help="tara, yayimlama")
    ap.add_argument("--sadece-uret", action="store_true", help="taramadan site uret")
    args = ap.parse_args()

    cfg = yapilandirma_yukle()
    bugun = datetime.now(timezone.utc).date()
    havuz = json_yukle(HAVUZ_YOLU, {})
    sayilar = json_yukle(SAYILAR_YOLU, [])
    durum = {"basarili": True, "mesaj": ""}

    if not args.sadece_uret:
        try:
            sorgu = sorgu_kur(cfg)
            log("PubMed taraniyor")
            pmidler = pmid_ara(sorgu, cfg["tarama"]["azami_kayit"])
            log(f"  {len(pmidler)} PMID bulundu")
            kayitlar = kayitlari_cek(pmidler) if pmidler else []
            yeni = havuzu_guncelle(havuz, kayitlar, cfg, bugun)
            dusen = havuzu_temizle(havuz, cfg, bugun)
            log(f"Havuz: +{yeni} yeni, -{dusen} suresi dolan, toplam {len(havuz)}")
        except Exception as e:  # noqa: BLE001
            # Sessiz basarisizlik yasak: site bunu gosterir.
            log(f"TARAMA BASARISIZ: {e}")
            durum = {"basarili": False,
                     "mesaj": "Bu hafta tarama tamamlanamadı. Liste güncellenmedi."}

    if args.kuru:
        adaylar = sayiyi_sec(havuz, cfg)
        print(f"\n--- KURU CALISMA: {len(adaylar)} kayit secilirdi ---")
        for k in adaylar:
            kat = kategori_bul(k["puan"], cfg, k["tipler"])
            print(f"\n[{kat['ad'] if kat else '-'}] {k['puan']} puan")
            print(f"  {k['baslik'][:110]}")
            print(f"  {k['dergi']} | {', '.join(k['konular']) or 'konu yok'}")
            print(f"  {' | '.join(k.get('gerekce', []))}")
        json_yaz(HAVUZ_YOLU, havuz)
        return

    if not args.sadece_uret and durum["basarili"]:
        secilen = sayiyi_sec(havuz, cfg)
        if secilen:
            no = len(sayilar) + 1
            for k in secilen:
                havuz[k["pmid"]]["sayi"] = no
            sayilar.append({
                "no": no,
                "tarih": bugun.isoformat(),
                "kayitlar": [havuz[k["pmid"]] for k in secilen],
            })
            log(f"Sayi {no}: {len(secilen)} kayit")
        else:
            log("Esigi gecen kayit yok. Sayi yayimlanmadi.")
            durum["mesaj"] = "Bu hafta eşiği geçen kayıt olmadı."

    json_yaz(HAVUZ_YOLU, havuz)
    json_yaz(SAYILAR_YOLU, sayilar)
    log("Site uretiliyor")
    siteyi_uret(cfg, sayilar, havuz, durum)
    log("Tamam")


if __name__ == "__main__":
    sys.exit(main())
