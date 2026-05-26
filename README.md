# Pallet-packer-3D

Desktopová aplikace pro výpočet a 3D vizualizaci rozložení balíků na paletě. Program pomáhá rychle ověřit, kolik kusů se vejde na zvolenou paletu při zadaném rozměru, hmotnosti, maximální výšce stohování a nosnosti palety.

Aplikace je napsaná v Pythonu, používá Tkinter pro GUI a Matplotlib pro 3D náhled.

## Funkce

- výběr přednastavených palet:
  - EUR 1200 × 800 mm,
  - IND 1200 × 1000 mm,
  - HALF 800 × 600 mm,
  - vlastní rozměr,
- zadání více typů balíků,
- nastavení rozměrů, hmotnosti, počtu kusů a barvy balíku,
- volitelné otáčení balíků ve 3 osách,
- výpočet rozmístění s ohledem na:
  - délku a šířku palety,
  - maximální výšku stohování,
  - maximální nosnost palety,
  - počet dostupných kusů,
- 3D vizualizace výsledného naložení,
- přepínání pohledu:
  - izometrický pohled,
  - pohled shora,
  - pohled zepředu,
- zapnutí/vypnutí hran balíků,
- zapnutí/vypnutí mřížky,
- zapnutí/vypnutí limitu výšky,
- legenda typů balíků,
- souhrn výsledku:
  - umístěné kusy,
  - neumístěné kusy,
  - celková hmotnost,
  - použitá výška,
  - objemové zaplnění.

## Instalace

### 1. Naklonování repozitáře

```bash
git clone https://github.com/uzivatel/pallet-packer-3d.git
cd pallet-packer-3d
```

### 2. Instalace závislostí

```bash
pip install matplotlib
```

Tkinter bývá součástí standardní instalace Pythonu. Pokud v Linuxu chybí, doinstaluj ho přes správce balíčků, například:

```bash
sudo apt install python3-tk
```

## Spuštění

```bash
python app.py
```

## Použití

1. Vyber typ palety nebo nastav vlastní rozměry.
2. Zadej maximální výšku stohování a nosnost palety.
3. Přidej jeden nebo více typů balíků.
4. U každého balíku nastav:
   - název,
   - délku,
   - šířku,
   - výšku,
   - hmotnost jednoho kusu,
   - počet kusů,
   - barvu v náhledu.
5. Podle potřeby povol nebo zakaž otáčení balíků ve 3 osách.
6. Klikni na **Spočítat a umístit**.
7. Výsledek zkontroluj v levém panelu a v 3D náhledu.

## Princip výpočtu

Program používá heuristický výpočet po vrstvách:

1. Z balíků vytvoří jednotlivé kusy podle zadaného počtu.
2. Pro každý kus připraví povolené orientace.
3. Skládá paletu po vodorovných vrstvách.
4. V každé vrstvě hledá vhodné umístění do volných obdélníků.
5. Z možných vrstev vybírá variantu s nejlepším využitím objemu, plochy a počtu kusů.
6. Pokračuje, dokud nedojde prostor, výška, nosnost nebo dostupné kusy.

Výpočet je navržený jako praktická heuristika, ne jako exaktní globální optimalizace. To znamená, že výsledek je rychlý a použitelný pro plánování, ale nemusí být matematicky nejlepší možná kombinace pro každý vstup.

## Technické poznámky

- Všechny rozměry jsou v milimetrech.
- Hmotnost je v kilogramech.
- 3D náhled je určený pro vizuální kontrolu rozložení, ne pro generování výrobní dokumentace.
- U většího počtu balíků může vypnutí hran v náhledu zrychlit vykreslování.
- Povolení rotace ve 3 osách může zvýšit využití prostoru, ale nemusí být vhodné pro zboží, které se nesmí pokládat na bok nebo vzhůru nohama.
