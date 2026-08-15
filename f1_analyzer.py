#!/usr/bin/env python3
"""
🏎️ Własny Analizator Telemetrii F1 (SRT CSV)
Czysta, modularna architektura z dynamicznym mapowaniem kolumn i wykresami.
"""
import argparse
import sys
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path


class F1TelemetryApp:
    def __init__(self, csv_path: str):
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            print(f"❌ Błąd: Nie znaleziono pliku {self.csv_path}")
            sys.exit(1)

        self.df = pd.DataFrame()
        self.lap_data = pd.DataFrame()
        self._load_data()

    def _load_data(self):
        """Ładuje dane, mapuje nazwy kolumn z SRT i wylicza prędkość"""
        print(f"📂 Wczytywanie pliku: {self.csv_path.name}...")
        try:
            # Używamy tabulatora (sep='\t') jako separatora!
            raw_df = pd.read_csv(self.csv_path, sep='\t', engine='pyarrow')
        except Exception:
            raw_df = pd.read_csv(self.csv_path, sep='\t', on_bad_lines='skip')

        column_aliases = {
            'lap': ['lapNum', 'Lap', 'CurrentLap', 'lap_num'],
            'throttle': ['throttle', 'Throttle'],
            'brake': ['brake', 'Brake'],
            'lap_time': ['lap_time', 'lap_time_s', 'LapTime']
        }

        mapped_cols = {}
        for internal_name, aliases in column_aliases.items():
            for alias in aliases:
                if alias in raw_df.columns:
                    mapped_cols[alias] = internal_name
                    break

        self.df = raw_df.rename(columns=mapped_cols)

        # Wyliczanie prędkości w km/h z wektorów prędkości, jeśli nie ma kolumny 'speed'
        if 'speed' not in self.df.columns and all(
                c in self.df.columns for c in ['velocity_X', 'velocity_Y', 'velocity_Z']):
            import numpy as np
            self.df['speed'] = np.sqrt(
                self.df['velocity_X'] ** 2 + self.df['velocity_Y'] ** 2 + self.df['velocity_Z'] ** 2) * 3.6

        if 'lap' in self.df.columns:
            self.df = self.df.dropna(subset=['lap'])
        else:
            print("❌ Brak kolumny określającej numer okrążenia (Lap/lapNum).")
            sys.exit(1)

        print("✅ Dane wczytane i zmapowane poprawnie!")

    def show_pace_analysis(self):
        """Wyświetla prostą analizę tempa w konsoli"""
        if 'lap' not in self.df.columns or 'lap_time' not in self.df.columns:
            print("⚠️ Brak danych o czasie okrążenia do analizy tempa.")
            return

        print("\n📊 --- ANALIZA TEMPA (TOP 10 OKRĄŻEŃ) ---")
        # Wyciągamy ostatni zarejestrowany czas dla każdego okrążenia
        pace = self.df.groupby('lap')['lap_time'].max().reset_index()
        pace = pace[pace['lap_time'] > 20]  # Odrzucamy błędy pomiarowe < 20s
        pace = pace.sort_values('lap_time').head(10)

        # Formatowanie do CLI
        print(f"{'Okrążenie':<15} | {'Czas (s)':<15}")
        print("-" * 33)
        for _, row in pace.iterrows():
            print(f"Lap {int(row['lap']):<11} | {row['lap_time']:.3f} s")
        print("-" * 33)

    def plot_telemetry(self, lap_number: int):
        """Generuje wykres telemetrii dla wybranego okrążenia"""
        lap_df = self.df[self.df['lap'] == lap_number]

        if lap_df.empty:
            print(f"❌ Brak danych dla okrążenia nr {lap_number}")
            return

        print(f"\n📈 Generowanie wykresu dla okrążenia nr {lap_number}...")

        # Tworzymy 2 wykresy jeden pod drugim
        sns.set_theme(style="darkgrid")
        fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
        fig.suptitle(f'Analiza Telemetrii - Okrążenie {lap_number}', fontsize=16)

        # Oś X - możemy użyć po prostu indeksu (jako "postęp" okrążenia)
        x_axis = range(len(lap_df))

        # 1. Wykres Prędkości
        if 'speed' in lap_df.columns:
            axes[0].plot(x_axis, lap_df['speed'], color='cyan', linewidth=2)
            axes[0].set_ylabel('Prędkość (km/h)')
            axes[0].set_title('Profil Prędkości')
        else:
            axes[0].text(0.5, 0.5, 'Brak danych o prędkości', ha='center', va='center')

        # 2. Wykres Inputów (Gaz/Hamulec)
        if 'throttle' in lap_df.columns:
            axes[1].plot(x_axis, lap_df['throttle'], color='green', label='Gaz')
        if 'brake' in lap_df.columns:
            axes[1].plot(x_axis, lap_df['brake'], color='red', label='Hamulec')

        axes[1].set_ylabel('Nacisk (0.0 - 1.0)')
        axes[1].set_xlabel('Czas / Ramki telemetrii')
        axes[1].legend(loc='upper right')
        axes[1].set_ylim(-0.05, 1.05)

        plt.tight_layout()
        plt.show()


def main():
    # Definicja naszego interfejsu CLI
    parser = argparse.ArgumentParser(
        description="🏎️ Twój Osobisty Analizator Telemetrii SRT",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument("-f", "--file", required=True, help="Ścieżka do pliku CSV z telemetrią")
    parser.add_argument("--pace", action="store_true", help="Wyświetl tabelę z najszybszymi okrążeniami")
    parser.add_argument("-p", "--plot", type=int, metavar="LAP", help="Wygeneruj wykres dla podanego okrążenia")

    args = parser.parse_args()

    # Inicjalizacja i logika
    app = F1TelemetryApp(args.file)

    if args.pace:
        app.show_pace_analysis()

    if args.plot:
        app.plot_telemetry(args.plot)

    if not args.pace and not args.plot:
        print("\n💡 Podpowiedź: Użyj flagi --pace aby zobaczyć czasy, lub -p [NUMER] aby narysować wykres.")
        print("Przykład: python f1_analyzer.py -f plik.csv --pace -p 3")


if __name__ == "__main__":
    main()