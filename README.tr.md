# pytest-collection-guard

Pytest'in topladığı (keşfettiği) test kimliklerini sürümler arasında karşılaştırır ve beklenmedik test kaybını CI hatasına çevirir.

"100 test geçti" demek, geçen testlerin *aynı* 100 test olduğu anlamına gelmez. Bir `testpaths` değişikliği, yanlış yazılmış bir yeniden adlandırma ya da parametrizasyonda kaybolan tek bir durum, test kümesini sessizce küçültürken koşu yine yeşil kalır. pytest-collection-guard, pytest'in *topladığı* test kimliklerini kaydeder ve beklenmeyen kaybı CI hatasına dönüştürür.

- **Türkçe** · [English (README.md)](README.md) ·
  [Terminal kaydı (docs/TERMINAL-RECORDING.md)](docs/TERMINAL-RECORDING.md)

## Neden

Pytest keşfi yapılandırmaya bağlıdır: `testpaths`, `norecursedirs` ve dosya/sınıf/fonksiyon adlandırma kuralları hangi testlerin toplanacağını belirler ([resmî keşif kuralları](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery)). Yapılandırma değişikliği toplanan test kümesini sessizce değiştirebilir; bazı dekoratör düzenleri tarihsel olarak testleri keşiften tamamen gizlemiştir ([pytest issue #10525](https://github.com/pytest-dev/pytest/issues/10525) — tarihsel bir örnek; bugünün pytest sürümü hakkında bir iddia değildir).

Mevcut araçlar toplama/sonuç verisini JSON'a aktarır ([pytest-json-report](https://github.com/numirias/pytest-json-report)) veya yeniden toplama farkını etkileşimli gösterir ([pytest-deck](https://mchalela/pytest-deck)). Bu projenin somut farkı: sürümlenmiş baz envanter, ortam profili, **gerekçeli kaldırma listesi** ve CI'da zorunlu kayıp denetimi. Hangi testlerin çalıştırılacağını asla değiştirmez.

## Kurulum

```console
$ python -m pip install .
```

Çalışma zamanı bağımlılığı: **yalnızca pytest** (bu bir pytest eklentisi; CLI yarısı yalnızca standart kütüphaneyi kullanır — `argparse`, `json`, `pathlib`, `platform`, `tomllib`). Geliştirme araçları (`ruff`, `mypy`, `pytest-cov`) `dev` eklentisiyle gelir.

## 30 saniyelik örnek

```console
$ pytest-collection-guard demo --dir demo
demo manifests written to demo/ (synthetic example data):
  demo/baseline.json  (4 selected tests)
  demo/current.json   (4 selected tests)

Both files contain 4 tests — but not the same 4: 'test_apply_discount' silently became 'test_apply_discount_v2'.

Now compare them:
  pytest-collection-guard compare demo/baseline.json demo/current.json

Expected: exit code 1, reporting test_apply_discount as REMOVED.

$ pytest-collection-guard compare demo/baseline.json demo/current.json
pytest-collection-guard compare
  baseline: demo/baseline.json (profile 'linux', 4 selected)
  current:  demo/current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

RESULT: FAIL — 1 unapproved removal(s); justify them in a removals TOML or restore the tests.

$ echo $?
1
```

Toplam sayı aynı kaldı (4 → 4), buna rağmen denetim başarısız: eklenen testler kaybı asla gizlemez.

## Gerçek iş akışı

Bilinen iyi bir revizyonda baz kaydedin, sonra her CI koşusunu bu baza karşı denetleyin. (`examples/lost-test/` bu senaryonun çalıştırılabilir bir kopyasıdır — aşağıdaki terminal kaydı gerçektir.)

```console
$ pytest --collect-only --collection-guard-out baseline.json --collection-guard-profile linux
...
collection-guard: manifest written to baseline.json (status: ok, 4 collected node id(s))
========================== 4 tests collected in 0.05s ==========================

$ pytest --collect-only --collection-guard-out current.json --collection-guard-profile linux
...
collection-guard: manifest written to current.json (status: ok, 4 collected node id(s))

$ pytest-collection-guard compare baseline.json current.json
pytest-collection-guard compare
  baseline: baseline.json (profile 'linux', 4 selected)
  current:  current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

RESULT: FAIL — 1 unapproved removal(s); justify them in a removals TOML or restore the tests.
```

### Gerçek bir kaldırma onaylama

Bir test *kasten* kaldırıldıysa, kod incelemesinden geçen bir TOML dosyasında gerekçelendirin:

```toml
# removals.toml — kod gibi incelenir; her kayıt bir gerekçe ister
[[removal]]
id = "tests/test_example_shop.py::test_apply_discount"
reason = "Feature dropped in 2.0 (issue #123, decided 2026-10-31)."
```

```console
$ pytest-collection-guard compare baseline.json current.json --allow removals.toml
...
APPROVED REMOVALS (1):
  - tests/test_example_shop.py::test_apply_discount
      reason: Feature dropped in 2.0 (issue #123, decided 2026-10-31).

RESULT: OK — no unapproved removals.
```

Kaldırımı **gerçekleşmemiş** bir izin kaydı `STALE ALLOW ENTRIES` olarak raporlanır; böylece dosya sessizce "her şeyi yok say" listesine dönüşemez.

## Çıkış kodları (CI kapısı)

| kod | anlam |
|-----|--------|
| `0` | onaysız kayıp yok (temiz ya da tüm kayıplar gerekçeli) |
| `1` | en az bir test onaysız kayboldu |
| `2` | karşılaştırma reddedildi: profil/toplama argümanı uyuşmazlığı, hatalı toplamadan kalan manifest ya da geçersiz girdi |

`2` kasıtlıdır: Linux envanterini Windows envanteriyle ya da `-k` süzgeçli koşuyu süzgeçsizle karşılaştırmak sahte kayıplar üretirdi — guard tahmin etmek yerine karşılaştırmayı reddeder.

## CI tarifi (GitHub Actions)

```yaml
- name: Collect inventory
  run: pytest --collect-only --collection-guard-out current.json --collection-guard-profile linux
- name: Check expected tests are still collected
  run: pytest-collection-guard compare ci/baseline.json current.json --allow ci/removals.toml
```

`ci/baseline.json` (profil başına bir tane!) ve `ci/removals.toml` dosyalarını depoya commit edin. `--json report.json` diğer araçlar için makine-okunur sonuç yazar.

## Neyin kaydedildiği

Manifest, iki tür veriyi kesinlikle ayırır:

- **kimlik (identity)** — sıralanmış `selected`/`deselected` test node kimlikleri. Karşılaştırılan veri budur. (Node kimlikleri rootdir'e görelidir; `test_checkout[paypal]` gibi parametre kimlikleri olduğu gibi kaydedilir.)
- **ortam (environment)** — profil etiketi, platform, Python/pytest sürümleri, rootdir ve toplamayı etkileyen argümanlar (`testpaths`, adlandırma kuralları, `norecursedirs`, konumsal argümanlar, `-k`, `-m`). Karşılaştırılabilirlik için yalnızca **profil** ve **toplama argümanları** denetlenir; geri kalanı insanlar için kaydedilir.

## Önemli davranış notları

- `--collect-only` toplamasında **test gövdeleri ve fixture'lar asla çalışmaz**.
- **Toplama, test modüllerinizi (ve `conftest.py`) import eder**; bu yüzden modül düzeyindeki yan etkiler çalışır. Test modüllerini import-safe tutun.
- **Toplama hatası geçerli envanter üretmez**: manifest `"status": "error"` ile yazılır ve `compare` onu reddeder (`2`). Yarım bir toplama asla "testler kayboldu" şeklinde davranamaz.
- **Guard test seçimini asla değiştirmez** — yalnızca toplamayı gözlemler.
- **Baz CI tarafından otomatik güncellenmez**; tazelemek incelenmiş, insan kararıdır.
- Platform, Python ve pytest sürümleri kaydedilir ama zorlanmaz; envanterler arası farka bakmak yerine **profil başına** bir baz kullanın.

## Bu araç ne değildir

- Kapsam ölçmez, eksik test üretmez, test çalıştırmasını hızlandırmaz.
- Test sayısının kaliteyi temsil ettiği iddiasında bulunmaz — tam tersi: sayıların kimlik kaybını gizlemesi yüzünden vardır.
- Rapor içeriği yereldir; parametre kimliklerine kişisel veri koyarsanız orada bulunabilir. Paketle gelen örnekler açıkça sentetik veri kullanır.

## Geliştirme

```console
$ python -m pip install -e ".[dev]"
$ bash scripts/check.sh        # lint + format + mypy strict + testler + ≥ %85 branch kapsam
$ python -m pytest --cov=pytest_collection_guard --cov-branch --cov-fail-under=85
```

Testler gerçek iç içe pytest oturumlarıyla (pytester) çalışır; hiçbiri ağ erişimi gerektirmez. Linux ve Windows CI'da kapsanır.

## Lisans

MIT — bkz. [LICENSE](LICENSE). Copyright (c) 2026 YusufBeratZengin.