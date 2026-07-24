HI-POT AMIDALA 1.0.5 - WDROZENIE

1. Nie nadpisuj produkcyjnych plikow amidala_config.json i hwid_map.json bez
   porownania ich z zatwierdzona konfiguracja stanowiska.
2. Podmien wszystkie pliki Python z paczki PATCH.
3. Usun katalogi build i dist.
4. Uruchom create_exe.py z interpretera .venv.
5. Kopiuj caly katalog dist\Hi-Pot Amidala.
6. Przed produkcja wykonaj wszystkie testy z AUDIT_RELEASE_REPORT.md.
7. W logu pierwszego uruchomienia musza wystapic wpisy KEYLOCK STATE='1' i VERIFY.
8. Brak ktoregokolwiek potwierdzenia oznacza: NIE WYDAWAC WERSJI.
