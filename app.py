import csv
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


TEMPLATES = {
    "B Tech SRN (1st Sem)": {
        "path": Path("B Tech SRN.tex"),
        "csv_placeholder": "Ex_1st_Sem_EC_W2025.csv",
    },
    "B Tech (3rd Sem)": {
        "path": Path("B Tech.tex"),
        "csv_placeholder": "3rd_Sem_CE_S2026_Ex.csv",
    },
}
DATE_PATTERN = re.compile(r"^\d{2}-\d{2}-\d{4}$")
SGPA_COLUMNS = [
    ("I", "sgpaOne"),
    ("II", "sgpaSecond"),
    ("III", "sgpaThird"),
    ("IV", "sgpaFourth"),
    ("V", "sgpaFifth"),
    ("VI", "sgpaSixth"),
    ("VII", "sgpaSeventh"),
    ("VIII", "sgpaEighth"),
    ("IX", "sgpaNinth"),
    ("X", "sgpaTenth"),
]
SEMESTER_ALIASES = {
    "1": "I",
    "01": "I",
    "FIRST": "I",
    "I": "I",
    "2": "II",
    "02": "II",
    "SECOND": "II",
    "II": "II",
    "3": "III",
    "03": "III",
    "THIRD": "III",
    "III": "III",
    "4": "IV",
    "04": "IV",
    "FOURTH": "IV",
    "IV": "IV",
    "5": "V",
    "05": "V",
    "FIFTH": "V",
    "V": "V",
    "6": "VI",
    "06": "VI",
    "SIXTH": "VI",
    "VI": "VI",
    "7": "VII",
    "07": "VII",
    "SEVENTH": "VII",
    "VII": "VII",
    "8": "VIII",
    "08": "VIII",
    "EIGHTH": "VIII",
    "VIII": "VIII",
    "9": "IX",
    "09": "IX",
    "NINTH": "IX",
    "IX": "IX",
    "10": "X",
    "TENTH": "X",
    "X": "X",
}


def is_valid_publish_date(value: str) -> bool:
    if not DATE_PATTERN.fullmatch(value or ""):
        return False
    try:
        datetime.strptime(value, "%d-%m-%Y")
    except ValueError:
        return False
    return True


def normalize_semester(value: str) -> str:
    cleaned = (value or "").strip().upper().replace("SEMESTER", "").replace("SEM", "").strip()
    return SEMESTER_ALIASES.get(cleaned, "")


def is_zero(value: str) -> bool:
    try:
        return float((value or "").strip()) == 0
    except ValueError:
        return False


def ensure_column(header: list[str], name: str) -> int:
    if name not in header:
        header.append(name)
    return header.index(name)


def write_csv_with_publish_date(uploaded_file, output_path: Path, publish_date: str) -> None:
    text = uploaded_file.getvalue().decode("utf-8-sig")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        raise ValueError("The uploaded CSV is empty.")

    header = [column.strip() for column in rows[0]]
    publish_index = ensure_column(header, "publish")
    incentive_indexes = [index for index, column in enumerate(header) if column == "incentive"]
    if not incentive_indexes:
        incentive_indexes = [ensure_column(header, "incentive")]
    semester_index = header.index("Semester") if "Semester" in header else None
    sgpa_index = header.index("sgpa") if "sgpa" in header else None
    sgpa_indexes = {roman: ensure_column(header, column) for roman, column in SGPA_COLUMNS}

    updated_rows = [header]
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))

        row[publish_index] = publish_date

        for incentive_index in incentive_indexes:
            if is_zero(row[incentive_index]):
                row[incentive_index] = "--"

        for index in sgpa_indexes.values():
            if not row[index].strip():
                row[index] = "--"

        if semester_index is not None and sgpa_index is not None:
            semester = normalize_semester(row[semester_index])
            if semester and row[sgpa_index].strip():
                row[sgpa_indexes[semester]] = row[sgpa_index].strip()

        updated_rows.append(row)

    if len(updated_rows) == 1:
        raise ValueError("The uploaded CSV has no student rows.")

    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(updated_rows)


def build_tex(template_path: Path, csv_placeholder: str, csv_name: str) -> str:
    tex = template_path.read_text(encoding="utf-8")
    return tex.replace("{" + csv_placeholder + "}", "{" + csv_name + "}")


def compile_pdf(uploaded_file, publish_date: str, template_name: str) -> tuple[bytes, str]:
    template = TEMPLATES[template_name]
    template_path = template["path"]
    csv_placeholder = template["csv_placeholder"]

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with tempfile.TemporaryDirectory(prefix="grade-card-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        csv_path = tmp_dir / "input.csv"
        tex_path = tmp_dir / "grade_card.tex"
        pdf_path = tmp_dir / "grade_card.pdf"

        write_csv_with_publish_date(uploaded_file, csv_path, publish_date)
        tex_path.write_text(
            build_tex(template_path, csv_placeholder, csv_path.name),
            encoding="utf-8",
        )

        background = template_path.parent / "Grade Card Ver 2.jpg"
        if background.exists():
            shutil.copy(background, tmp_dir / background.name)

        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tmp_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if result.returncode != 0 or not pdf_path.exists():
            raise RuntimeError(result.stdout)

        return pdf_path.read_bytes(), result.stdout


def main() -> None:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Streamlit is not installed. Install it with `pip install streamlit` "
            "and run `streamlit run app.py`."
        ) from exc

    st.set_page_config(page_title="Grade Card Builder", page_icon="📄")
    st.title("Grade Card Builder")
    st.write("Choose a grade-card template, upload a CSV, enter the publishing date in `dd-mm-yyyy` format, and generate PDF output.")

    template_name = st.selectbox("Grade card type", list(TEMPLATES.keys()))
    uploaded_csv = st.file_uploader("CSV input", type=["csv"])
    publish_date = st.text_input("Publishing date", placeholder="dd-mm-yyyy")

    if publish_date and not is_valid_publish_date(publish_date):
        st.error("Publishing date must be a real date in dd-mm-yyyy format, for example 13-12-2025.")

    can_build = uploaded_csv is not None and is_valid_publish_date(publish_date)

    if st.button("Build grade card PDF", disabled=not can_build):
        try:
            with st.spinner("Generating PDF..."):
                pdf_bytes, latex_log = compile_pdf(uploaded_csv, publish_date, template_name)
            st.success("Grade card PDF generated successfully.")
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name="grade_card.pdf",
                mime="application/pdf",
            )
            with st.expander("LaTeX build log"):
                st.code(latex_log)
        except Exception as exc:
            st.error("Could not generate the PDF.")
            st.code(str(exc))


if __name__ == "__main__":
    main()
