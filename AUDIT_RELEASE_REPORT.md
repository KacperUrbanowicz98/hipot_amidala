# Hi-Pot Amidala 1.0.5 — raport audytu przed wydaniem

Data audytu: 2026-07-24

## Status

Wersja 1.0.5 jest **kandydatem do testów akceptacyjnych na stanowisku**, a nie wersją, której można zagwarantować całkowity brak błędów. Audyt kodu zakończył się pozytywnie, ale finalne wydanie wymaga przejścia testów z rzeczywistą Chromą 19052, Arduino, fixture i wszystkimi rodzinami produktu.

## Zakres

Przejrzano 14 skryptów Python, łącznie 5624 linie:

- `main.py`
- `gui.py`
- `config.py`
- `admin_panel.py`
- `test_screen.py`
- `hipot_device.py`
- `interlock.py`
- `logger.py`
- `settings_manager.py`
- `hwid_map.py`
- `safety_rules.py`
- `runtime_logging.py`
- `create_exe.py`
- `release_selftest.py`

Sprawdzono również `amidala_config.json`, `hwid_map.json` i proces budowania ONEDIR.

## Najważniejsze zabezpieczenia w wersji 1.0.5

1. **Fałszywy PASS pustego fixture**
   - efektywny dolny limit Chromy wynosi co najmniej 0.500 mA,
   - PASS wymaga co najmniej dwóch pomiarów na żywo w zatwierdzonym zakresie,
   - wymagane jest prawidłowe napięcie końcowe i brak przekroczenia limitu HIGH.

2. **Stary wynik `RESULT:LAST`**
   - przed START wykonywany jest STOP i pomiar bazowy,
   - nowy cykl musi zostać potwierdzony przez `TESTING/RUNNING` albo świeże narastanie napięcia,
   - wynik `LAST` można odczytać tylko raz i wyłącznie dla potwierdzonego cyklu,
   - podejrzanie szybki PASS jest odrzucany.

3. **Konfiguracja Chromy**
   - każda komenda jest sprawdzana przez `SYST:ERR?`,
   - po konfiguracji wykonywany jest odczyt zwrotny napięcia, LOW, HIGH oraz czasów,
   - rozbieżność lub brak odpowiedzi blokuje test.

4. **Interlock aplikacyjny**
   - nie istnieje produkcyjny tryb ręczny omijający Arduino,
   - wymagane jest świeże przejście `OPEN -> CLOSED`,
   - brak heartbeat lub błąd portu powoduje STOP i blokadę,
   - otwarcie klapy podczas aktywnego cyklu powoduje STOP,
   - otwarcie już po terminalnym statusie nie kasuje prawidłowego wyniku.

5. **Sterowanie lokalne Chromy**
   - podczas sesji aplikacja ustawia `SYST:KLOC ON` i sprawdza `SYST:KLOC? == 1`,
   - zapobiega to zmianie ustawień z panelu między konfiguracją i START,
   - przy rozłączeniu aplikacja wykonuje STOP i zwalnia panel przez `SYST:KLOC OFF`.

6. **Błędy aplikacji i EXE**
   - krytyczny wyjątek Tk powoduje awaryjny STOP i zamknięcie aplikacji,
   - build `--windowed` zapisuje stdout/stderr do `app_runtime_logs`,
   - konfiguracja i mapa HWID są walidowane w całości przed użyciem,
   - pliki JSON i raporty są publikowane atomowo,
   - builder używa wyłącznie dokładnych nazw plików i przypiętych wersji zależności.

## Automatyczne kontrole zakończone powodzeniem

- kompilacja wszystkich plików przez `py_compile`,
- 8 grup testów regresyjnych bez sprzętu,
- blokada fałszywego PASS pustego fixture,
- akceptacja poprawnego PASS,
- akceptacja wczesnego FAIL,
- odrzucenie wczesnego PASS,
- odrzucenie starego `LAST`,
- potwierdzenie readbacku profilu i odrzucenie rozbieżności,
- heartbeat interlocka i utrata połączenia,
- wymagane `OPEN -> CLOSED`,
- symulacja `stdout=None` i `stderr=None` dla builda windowed,
- walidacja konfiguracji oraz mapy HWID,
- analiza AST: brak `eval`, `exec` i `shell=True`,
- import wszystkich modułów,
- przygotowanie katalogu staging buildera.

## Warunki wydania — wszystkie obowiązkowe

### Test funkcjonalny na docelowym stanowisku

1. Uruchomić aplikację i potwierdzić w logu:
   - `[KEYLOCK] ... STATE='1'`
   - `[VERIFY] Profil ACW odczytany zwrotnie ...`
2. Wykonać co najmniej 10 testów pustego fixture — wszystkie muszą zakończyć się FAIL kod 18.
3. Wykonać serię poprawnych sztuk **dla każdej rodziny modelu i każdego fixture**.
4. Potwierdzić, że najniższy prąd dobrej sztuki ma bezpieczny margines powyżej 0.500 mA.
5. Wykonać zatwierdzoną próbkę FAIL dla przekroczenia HIGH / przebicia.
6. Otworzyć klapę podczas rampy — wymagany natychmiastowy STOP i blokada.
7. Odłączyć Arduino podczas rampy — wymagany STOP i blokada.
8. Odłączyć RS232 podczas rampy — wymagany STOP i blokada.
9. Nacisnąć STOP ręcznie — wynik nie może zostać zapisany jako PASS/FAIL produktu.
10. Zamknąć aplikację podczas testu — wymagane ostrzeżenie oraz STOP po potwierdzeniu.
11. Wykonać kilka cykli bez zamykania aplikacji i potwierdzić rosnące `cycle_id`.
12. Uruchomić gotowe EXE, nie tylko `main.py`, i powtórzyć test pusty/dobra sztuka.

### Parametry wymagające potwierdzenia procesowego

- Jeden wspólny profil ACW jest używany dla wszystkich modeli z mapy HWID. Należy potwierdzić, że 4 kV, 2.5 mA, próg 0.500 mA i czasy są zatwierdzone dla każdej rodziny.
- `Frequency`, `Arc Sense` i `Continuity` nie są obecnie programowane ani odczytywane zwrotnie przez aplikację. Muszą zostać ustawione i zweryfikowane na Chroma zgodnie z instrukcją procesu.
- Próg 0.500 mA został potwierdzony na wykonanej serii, ale przed wydaniem musi być zwalidowany dla wszystkich poprawnych wariantów produktu.

## Znane ryzyka nieblokujące samego wyniku Hi-Pot

- Hasło panelu administracyjnego jest zapisane w kodzie; jest to ryzyko dostępu do ustawień, nie mechanizmu klasyfikacji PASS/FAIL.
- Zapis raportu jest wykonywany w tle. Awaria obu lokalizacji raportu jest sygnalizowana operatorowi, ale nie zmienia wyniku elektrycznego.
- Automatyczne testy nie zastępują testu z firmware 5.14 i rzeczywistym okablowaniem stanowiska.

## Budowanie

```powershell
cd "C:\Users\kacper.urbanowicz\PycharmProjects\hipot_amidala"

& ".\.venv\Scripts\python.exe" -m pip install -r .\requirements-build.txt
Remove-Item -Recurse -Force .\build, .\dist -ErrorAction SilentlyContinue
& ".\.venv\Scripts\python.exe" .\create_exe.py
```

Builder przed utworzeniem EXE sam uruchamia kompilację, regresje i kontrolę konfiguracji. Należy kopiować cały katalog `dist\Hi-Pot Amidala`, nie samo EXE.

## Decyzja audytowa

Kod może przejść do **testów akceptacyjnych v1.0.5**. Wydanie produkcyjne jest dopuszczalne dopiero po podpisaniu wyników powyższej listy testów na docelowym stanowisku.
