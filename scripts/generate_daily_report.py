#!/usr/bin/env python3
"""
generate_daily_report.py - Gerador de Relatório Noturno de CFTV (21:00).
- Consulta os eventos gravados no SQLite do pendrive.
- Gera gráfico de série temporal das detecções ao longo do dia com matplotlib.
- Compila documento executivo em PDF com ReportLab contendo métricas e galeria de frames.
- Salva no pendrive (/mnt/pendrive_cinza/cftv_events/reports/) e envia via ntfy como anexo.
"""

import os
import sys
import shutil
import sqlite3
import argparse
import urllib.request
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Headless backend para rodar no Linux sem interface gráfica
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

STORAGE_DIR = os.getenv("STORAGE_DIR", "/mnt/pendrive_cinza/cftv_events")
FALLBACK_STORAGE_DIR = os.path.expanduser("~/cftv_events")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "bruno-casa-dallas")

def get_base_dir() -> Path:
    p = Path(STORAGE_DIR)
    if p.exists() and (p / "events.db").exists():
        return p
    fb = Path(FALLBACK_STORAGE_DIR)
    return fb if fb.exists() else p

def query_daily_events(db_path: Path, target_date: str) -> list:
    """Consulta todos os eventos registrados para a data especificada."""
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, date, time, channel_id, channel_name, event_type, image_path, file_size
            FROM events
            WHERE date = ?
            ORDER BY time ASC
        """, (target_date,))
        return [dict(row) for row in cursor.fetchall()]

def generate_timeseries_plot(events: list, target_date: str, output_path: Path) -> bool:
    """Gera um gráfico elegante de distribuição temporal dos eventos ao longo das horas do dia."""
    try:
        hours = list(range(24))
        # Contagem por canal e por hora
        channels = sorted(list(set(e["channel_name"] for e in events))) if events else ["Geral"]
        channel_counts = {ch: [0]*24 for ch in channels}

        for ev in events:
            time_part = ev["time"]
            hour = int(time_part.split(":")[0])
            ch = ev["channel_name"]
            if 0 <= hour < 24 and ch in channel_counts:
                channel_counts[ch][hour] += 1

        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
        fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)

        # Paleta moderna
        palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
        bottom = [0] * 24

        for idx, ch in enumerate(channels):
            counts = channel_counts[ch]
            color = palette[idx % len(palette)]
            ax.bar(hours, counts, bottom=bottom, label=ch, color=color, alpha=0.85, width=0.65, edgecolor="white")
            bottom = [b + c for b, c in zip(bottom, counts)]

        ax.set_title(f"Série Temporal de Detecções de Pessoas - {target_date}", fontsize=14, fontweight="bold", pad=12)
        ax.set_xlabel("Hora do Dia (00:00 às 23:59)", fontsize=11, labelpad=8)
        ax.set_ylabel("Quantidade de Detecções", fontsize=11, labelpad=8)
        ax.set_xticks(hours)
        ax.set_xticklabels([f"{h:02d}h" for h in hours], fontsize=9)
        ax.set_ylim(bottom=0)
        ax.grid(axis="y", linestyle="--", alpha=0.5)

        # Destaca o corte das 21h se relevante
        ax.axvline(x=21, color="#e74c3c", linestyle=":", linewidth=1.5, label="Horário de Emissão (21h)")

        ax.legend(loc="upper right", frameon=True, facecolor="#f8f9fa", edgecolor="#ced4da", fontsize=9)
        plt.tight_layout()
        fig.savefig(output_path, format="png")
        plt.close(fig)
        return True
    except Exception as e:
        print(f"Erro ao gerar gráfico de série temporal: {e}")
        return False

def generate_pdf_report(events: list, target_date: str, plot_img_path: Path, output_pdf: Path, disk_info: dict) -> bool:
    """Compila o relatório executivo em PDF usando ReportLab."""
    try:
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(output_pdf),
            pagesize=A4,
            leftMargin=1.5*cm,
            rightMargin=1.5*cm,
            topMargin=1.5*cm,
            bottomMargin=1.5*cm
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#1a252f"),
            fontName="Helvetica-Bold",
            spaceAfter=4
        )
        subtitle_style = ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#7f8c8d"),
            spaceAfter=15
        )
        h2_style = ParagraphStyle(
            "SectionH2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#2c3e50"),
            fontName="Helvetica-Bold",
            spaceBefore=12,
            spaceAfter=8
        )
        body_style = ParagraphStyle(
            "BodyTextCustom",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#34495e")
        )

        elements = []

        # Cabeçalho
        elements.append(Paragraph("🛡️ Relatório Diário de Segurança CFTV", title_style))
        elements.append(Paragraph(f"Homelab Dallas | Auditoria Noturna de Eventos - <b>{target_date}</b>", subtitle_style))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#3498db"), spaceAfter=15))

        # Indicadores Executivos
        total_events = len(events)
        humans_count = sum(1 for e in events if "human" in e.get("event_type", "").lower() or "face" in e.get("event_type", "").lower())
        motion_count = total_events - humans_count

        if total_events > 0:
            ch_counter = {}
            for e in events:
                ch_counter[e["channel_name"]] = ch_counter.get(e["channel_name"], 0) + 1
            most_active_channel = max(ch_counter.items(), key=lambda x: x[1])[0]
            first_event = events[0]["time"]
            last_event = events[-1]["time"]
        else:
            most_active_channel = "N/A"
            first_event = "N/A"
            last_event = "N/A"

        event_summary_str = f"{total_events} ({humans_count} humanos, {motion_count} mov.)" if total_events > 0 else "0"

        metrics_data = [
            ["Métrica Analisada", "Valor Registrado", "Métrica de Infraestrutura", "Status"],
            ["Total de Ocorrências", event_summary_str, "Armazenamento Pendrive", f"{disk_info.get('free_gb', '0')} GB livres ({disk_info.get('used_pct', '0%')})"],
            ["Canal com Maior Atividade", most_active_channel, "Cluster Homelab", "Nó Alpine (192.168.1.7)"],
            ["Primeiro Registro do Dia", first_event, "NVR Xiongmai", "Online (Read-Only)"],
            ["Último Registro do Dia", last_event, "Gateway WebRTC", "go2rtc (Nó Peixe)"]
        ]

        t = Table(metrics_data, colWidths=[5.0*cm, 3.5*cm, 5.0*cm, 4.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 15))

        # Seção do Gráfico de Série Temporal
        elements.append(Paragraph("📊 Distribuição Temporal das Detecções (00h às 21h)", h2_style))
        if plot_img_path and plot_img_path.exists():
            elements.append(RLImage(str(plot_img_path), width=18*cm, height=8.1*cm))
        else:
            elements.append(Paragraph("<i>Nenhum gráfico gerado para o período.</i>", body_style))

        elements.append(Spacer(1, 15))

        # Seção de Galeria de Evidências
        elements.append(Paragraph("📷 Galeria de Frames Capturados (Amostras de Detecção de Pessoas)", h2_style))
        if total_events == 0:
            elements.append(Paragraph("<i>Nenhuma pessoa identificada ou presença anômala registrada no período de monitoramento. Perímetro seguro.</i>", body_style))
        else:
            # Seleciona até 6 amostras representativas distribuídas ao longo dos eventos
            sample_count = min(6, total_events)
            step = max(1, total_events // sample_count)
            selected_samples = [events[i * step] for i in range(sample_count)]

            # Monta grid 2 colunas com imagens e legendas
            gallery_rows = []
            cur_row = []
            for ev in selected_samples:
                img_path = Path(ev["image_path"])
                if img_path.exists():
                    label = Paragraph(f"<b>{ev['time']}</b> | {ev['channel_name']}", body_style)
                    img_flow = RLImage(str(img_path), width=8.2*cm, height=4.8*cm)
                    cell = [img_flow, Spacer(1, 3), label]
                else:
                    cell = [Paragraph(f"<i>Frame ausente: {img_path.name}</i>", body_style)]

                cur_row.append(cell)
                if len(cur_row) == 2:
                    gallery_rows.append(cur_row)
                    cur_row = []
            if cur_row:
                cur_row.append([])
                gallery_rows.append(cur_row)

            if gallery_rows:
                g_table = Table(gallery_rows, colWidths=[9.0*cm, 9.0*cm])
                g_table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]))
                elements.append(g_table)

        doc.build(elements)
        print(f"✅ Relatório PDF gerado com sucesso em: {output_pdf}")
        return True
    except Exception as e:
        print(f"Erro ao compilar relatório PDF: {e}")
        return False

def send_pdf_to_ntfy(pdf_path: Path, target_date: str, total_events: int):
    """Envia o arquivo PDF compilado como anexo via ntfy."""
    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    filename = pdf_path.name
    title = f"📊 Relatório CFTV 21h: {total_events} pessoas detectadas ({target_date})"
    message = f"Relatório diário consolidado com gráfico temporal e galeria de fotos. {total_events} eventos registrados."

    headers = {
        "Title": title.encode("utf-8"),
        "Message": message.encode("utf-8"),
        "Filename": filename,
        "Priority": "default",
        "Tags": "chart_with_upwards_trend,page_facing_up,shield"
    }

    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        req = urllib.request.Request(url, data=pdf_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                print(f"📱 Relatório PDF entregue com sucesso no app ntfy ({url})!")
                return True
    except Exception as e:
        print(f"Falha ao enviar relatório via ntfy: {e}")
    return False

def get_disk_info(path: Path) -> dict:
    try:
        total, used, free = shutil.disk_usage(path)
        free_gb = round(free / (1024**3), 2)
        used_pct = f"{round((used / total) * 100, 1)}%"
        return {"free_gb": free_gb, "used_pct": used_pct}
    except Exception:
        return {"free_gb": "N/A", "used_pct": "N/A"}

def main():
    parser = argparse.ArgumentParser(description="Gerador de Relatório Diário CFTV às 21h")
    parser.add_argument("--date", help="Data no formato YYYY-MM-DD (padrão: hoje)")
    parser.add_argument("--no-ntfy", action="store_true", help="Não envia o PDF para o ntfy")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    base_dir = get_base_dir()
    db_path = base_dir / "events.db"
    reports_dir = base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Consultando eventos para {target_date} em {db_path}...")
    events = query_daily_events(db_path, target_date)
    print(f"Encontrados {len(events)} eventos de detecção.")

    # 1. Gera gráfico de série temporal
    plot_img_path = Path(f"/tmp/timeseries_{target_date}.png")
    generate_timeseries_plot(events, target_date, plot_img_path)

    # 2. Gera PDF consolidado
    output_pdf = reports_dir / f"relatorio_cftv_{target_date}.pdf"
    disk_info = get_disk_info(base_dir)
    pdf_ok = generate_pdf_report(events, target_date, plot_img_path, output_pdf, disk_info)

    # 3. Envia para o ntfy
    if pdf_ok and not args.no_ntfy:
        send_pdf_to_ntfy(output_pdf, target_date, len(events))

if __name__ == "__main__":
    main()
