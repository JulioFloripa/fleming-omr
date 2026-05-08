"""
test_reader.py — Testes de integração Fleming OMR v5.

Uso:
  python3 test_reader.py                          # testa config + gerador
  python3 test_reader.py samples/julio.jpg        # testa com imagem real
"""

import sys
import json
from pathlib import Path


def test_config():
    from app.config import (
        get_all_bubble_centers_mm,
        get_all_bubble_centers_px,
        get_language_centers_mm,
        get_language_centers_px,
        export_grid_json,
        TOTAL_QUESTIONS,
        BUBBLE_RADIUS_MM,
        SAMPLE_RADIUS_MULT,
        mm_to_px,
    )

    mm = get_all_bubble_centers_mm()
    px = get_all_bubble_centers_px()

    assert len(mm) == TOTAL_QUESTIONS, f"Esperado {TOTAL_QUESTIONS}, obtido {len(mm)}"
    for q in range(1, TOTAL_QUESTIONS + 1):
        assert q in mm
        for alt in ["A", "B", "C", "D"]:
            assert alt in mm[q]
            x, y = mm[q][alt]
            assert 0 < x < 210, f"Q{q}{alt} x={x}mm fora"
            assert 0 < y < 297, f"Q{q}{alt} y={y}mm fora"

    # Verificar sobreposições
    all_pts = [(px[q][a], f"Q{q}{a}") for q in px for a in px[q]]
    for i in range(len(all_pts)):
        for j in range(i + 1, len(all_pts)):
            dx = abs(all_pts[i][0][0] - all_pts[j][0][0])
            dy = abs(all_pts[i][0][1] - all_pts[j][0][1])
            assert dx > 15 or dy > 15, f"Sobreposição: {all_pts[i][1]} e {all_pts[j][1]}"

    # Línguas
    lang_mm = get_language_centers_mm()
    lang_px = get_language_centers_px()
    assert len(lang_mm) >= 2
    assert "Inglês" in lang_mm
    assert "Espanhol" in lang_mm

    r_sample = int(mm_to_px(BUBBLE_RADIUS_MM) * SAMPLE_RADIUS_MULT)

    print(f"✅ Config: {TOTAL_QUESTIONS} questões, 4 alternativas")
    print(f"   Q1.A  = {px[1]['A']}px")
    print(f"   Q63.D = {px[63]['D']}px")
    print(f"   Raio real = {int(mm_to_px(BUBBLE_RADIUS_MM))}px, amostragem = {r_sample}px")
    print(f"   Línguas: {lang_px}")
    print(f"   Grid JSON: {len(json.dumps(export_grid_json()))} bytes")


def test_generator():
    from generator.sheet_generator import generate_sheet_for_student

    pdf = generate_sheet_for_student(
        template_type="ACAFE",
        student_id="1110",
        student_name="Julio Souza",
        student_sede="Florianópolis",
    )

    out = Path("output")
    out.mkdir(exist_ok=True)
    path = out / "teste_gabarito.pdf"
    path.write_bytes(pdf)
    print(f"✅ Gerador: {path} ({len(pdf)} bytes)")


def test_reader(image_path: str):
    from scanner.omr_reader import OMRReader
    from app.config import TOTAL_QUESTIONS

    reader = OMRReader()
    debug_path = str(Path(image_path).with_suffix(".debug.png"))
    result = reader.read(image_path, debug_path=debug_path)

    print(f"\n{'=' * 60}")
    print(f"Resultado: {image_path}")
    print(f"{'=' * 60}")
    print(f"  Success:     {result.success}")
    print(f"  Template:    {result.template_id}")
    print(f"  Aluno:       {result.student_id}")
    print(f"  Tipo:        {result.template_type}")
    print(f"  Língua:      {result.language}")
    print(f"  Respostas:   {len(result.answers)}/{TOTAL_QUESTIONS}")
    print(f"  Erros:       {len(result.errors)}")

    if result.answers:
        print(f"\n  Respostas:")
        for q in sorted(result.answers.keys()):
            print(f"    Q{q}: {result.answers[q]}")

    if result.errors:
        print(f"\n  Erros:")
        for e in result.errors:
            print(f"    ⚠ {e}")

    print(f"\n  Debug: {debug_path}")


if __name__ == "__main__":
    test_config()
    test_generator()

    if len(sys.argv) > 1:
        test_reader(sys.argv[1])
    else:
        print("\n💡 Para testar com imagem:")
        print("   python3 test_reader.py samples/julio.jpg")
