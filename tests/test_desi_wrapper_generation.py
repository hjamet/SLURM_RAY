"""
Test pour vérifier que le wrapper DESI généré ne contient pas d'erreur NameError.

Ce test vérifie que la méthode _write_desi_wrapper() génère un code Python valide
sans référence à des variables non définies (comme 'retries' qui était référencé
dans un f-string mais non défini dans le scope).
"""

import os
import sys
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_desi_wrapper_generation():
    """Test que le wrapper généré est syntaxiquement valide et ne contient pas de NameError"""
    
    # Lire directement le code source de la méthode _write_desi_wrapper
    desi_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "slurmray", "backend", "desi.py"
    )
    
    with open(desi_file, "r") as f:
        desi_code = f.read()
    
    # Extraire le contenu du f-string qui génère le wrapper
    # Chercher la méthode _write_desi_wrapper
    start_marker = "def _write_desi_wrapper(self, filename):"
    start_idx = desi_code.find(start_marker)
    assert start_idx != -1, "Could not find _write_desi_wrapper method"
    
    # Trouver le début du f-string (content = f""")
    content_start = desi_code.find('content = f"""', start_idx)
    assert content_start != -1, "Could not find content = f\"\"\""
    
    # Trouver la fin du f-string (""")
    # Chercher la prochaine occurrence de """ après content = f"""
    content_end = desi_code.find('"""', content_start + len('content = f"""'))
    assert content_end != -1, "Could not find end of f-string"
    
    # Extraire le template (avec les {{ }} échappés dans le code source)
    template = desi_code[content_start + len('content = f"""'):content_end]
    
    # Vérifier que le template contient bien les échappements dans le code source
    assert "{{retries}}" in template, "Template should contain {{retries}} for escaping in source code"
    assert "{{MAX_RETRIES}}" in template, "Template should contain {{MAX_RETRIES}} for escaping in source code"
    
    # Simuler ce que Python ferait avec le f-string (remplacer {{ par { et }} par })
    # C'est ce qui se passe quand le f-string est évalué
    generated_code = template.replace("{{", "{").replace("}}", "}")
    
    # Vérifier que le code généré contient les bonnes références (sans échappement)
    assert "{retries}" in generated_code, "Generated code should contain {retries} (unescaped)"
    assert "{MAX_RETRIES}" in generated_code, "Generated code should contain {MAX_RETRIES} (unescaped)"
    
    # Vérifier que le code généré ne contient PAS les accolades doubles
    assert "{{retries}}" not in generated_code, "Generated code should not contain escaped {{retries}}"
    assert "{{MAX_RETRIES}}" not in generated_code, "Generated code should not contain escaped {{MAX_RETRIES}}"
    
    # Vérifier que le code peut être compilé (syntaxiquement valide)
    try:
        compile(generated_code, "desi_wrapper.py", "exec")
        print("✅ Generated wrapper code is syntactically valid")
    except SyntaxError as e:
        print(f"❌ ERROR: Generated code has syntax error: {e}")
        print(f"   Line {e.lineno}: {e.text}")
        if e.text:
            print(f"   Code: {e.text.strip()}")
        raise
    except NameError as e:
        print(f"❌ ERROR: Generated code has NameError (variable not defined): {e}")
        print(f"   This is the bug we're trying to fix!")
        raise
    
    # Vérifier que les variables sont bien définies dans le scope approprié
    assert "retries = 0" in generated_code, "Variable 'retries' should be initialized in main()"
    assert "MAX_RETRIES = 1000" in generated_code, "Constant 'MAX_RETRIES' should be defined"
    
    # Vérifier que les f-strings utilisent bien les variables définies
    # Le code généré devrait contenir: f"⏳ Still waiting... (attempt {retries}/{MAX_RETRIES})"
    assert 'f"⏳ Still waiting... (attempt {retries}/{MAX_RETRIES})"' in generated_code, \
        "Generated code should contain f-string with {retries} and {MAX_RETRIES}"
    
    # Vérifier aussi la ligne 482 avec le calcul
    assert 'f"❌ Timeout: Could not acquire lock after {MAX_RETRIES} attempts' in generated_code, \
        "Generated code should contain timeout message with {MAX_RETRIES}"
    
    print("✅ All wrapper generation tests passed!")
    print(f"   ✓ Template contains proper escaping: {{retries}} and {{MAX_RETRIES}}")
    print(f"   ✓ Generated code is valid Python and uses variables correctly")
    print(f"   ✓ Generated code size: {len(generated_code)} bytes")
    print(f"   ✓ No NameError: variables are properly defined in scope")


if __name__ == "__main__":
    test_desi_wrapper_generation()
    print("\n✅ Test completed successfully!")

