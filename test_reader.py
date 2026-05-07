from scanner.omr_reader import OMRReader

reader = OMRReader()

result = reader.read(
    "samples/julio.jpg",
    debug_path="samples/debug_reader.jpg"
)

print("\n===== RESULTADO =====\n")

print("Success:", result.success)
print("Template:", result.template_id)
print("Student:", result.student_id)

print("\nAnswers:")
for q, ans in sorted(result.answers.items()):
    print(f"{q}: {ans}")

print("\nErrors:")
for e in result.errors:
    print("-", e)

print("\nDebug salvo em:")
print("samples/debug_reader.jpg")