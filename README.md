# Aquael aqu@rium

Nieoficjalny komponent Home Assistant dla urządzeń Aquael aqu@rium / Aquael Link.

Integracja działa lokalnie w sieci LAN i udostępnia urządzenia Aquael jako encje
Home Assistant. Repozytorium jest przygotowane jako prywatne repo HACS typu
`Integration`.

## Obsługiwane urządzenia

- HyperMAX Link ECU
- Thermometer Link
- Light Link
- Socket Link Duo

## Funkcje

- Automatyczne wykrywanie urządzeń Aquael Link w sieci lokalnej.
- Encje Home Assistant dla temperatur, przełączników, nastaw, trybów i diagnostyki.
- Panel boczny `/aquael-link` dla HyperMAX i Thermometer Link.
- Lokalna komunikacja UDP bez chmury Aquael.

## Instalacja przez HACS

1. W HACS wybierz `Custom repositories`.
2. Dodaj adres tego repozytorium jako typ `Integration`.
3. Zainstaluj `Aquael aqu@rium`.
4. Uruchom ponownie Home Assistant.
5. Dodaj integrację z ekranu `Settings > Devices & services`.

## Uwagi

To nie jest oficjalna integracja Aquael. Projekt nie jest powiązany z producentem.
Używasz go na własną odpowiedzialność w lokalnym środowisku Home Assistant.

## Wymagania

- Home Assistant 2024.12 lub nowszy.
- HACS.
- Urządzenia Aquael Link dostępne w tej samej sieci lokalnej.
