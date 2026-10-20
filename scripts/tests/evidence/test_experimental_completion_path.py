"""GEN-005F1 — decisão Astra: um único caminho técnico de conclusão.

Antes desta mudança, ``scripts/evidence/run.sh`` pulava export/validate/
finalize inteiramente para runs experimentais. Depois de remover esse
desvio, ``export_evidence.py``, ``validate_run_artifacts.py`` e
``finalize_run.py`` precisam validar a identidade de política *experimental*
gravada no documento — e não a política pública padrão, carregada por
omissão sempre que nenhuma política é passada explicitamente.

Estes testes usam fixtures pequenas (uma política experimental isolada,
materializada em um diretório temporário por
``validation.experimental_policy.materialize_experimental_policy``, e um
documento ``NOT_EVALUABLE`` mínimo) para comprovar, sem side effects e sem
qualquer subprocesso de 30 minutos, que:

* threading explícito da política certa (pública ou experimental) faz a
  validação aceitar o documento correspondente;
* a ativação pública padrão nunca é substituída silenciosamente — sem
  threading explícito, o comportamento histórico (validar contra a política
  pública) permanece intacto, o que é exatamente por isso que um documento
  com identidade experimental é rejeitado nesse caso.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "evidence"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from activation_policy import load_public_activation_policy, policy_identity  # noqa: E402
from evidence_contract import not_evaluable_document, promote_for_public_output, validate_document  # noqa: E402
from validation.experimental_policy import materialize_experimental_policy  # noqa: E402

import export_evidence  # noqa: E402
import finalize_run  # noqa: E402
import validate_run_artifacts  # noqa: E402


def _experimental_fixture(out_dir: Path) -> dict:
    return materialize_experimental_policy(
        parameters={"support.minimum_mapq": 5}, parameter_set_id="f1-fixture", out_dir=out_dir,
    )


class ExperimentalCompletionPathTests(unittest.TestCase):
    def test_not_evaluable_document_carries_the_experimental_identity_when_a_policy_is_given(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            from activation_policy import load_experimental_activation_policy

            experimental_policy = load_experimental_activation_policy(
                paths["activation"], profiles_path=paths["profiles"],
            )
            document = not_evaluable_document(
                "sample-f1", "run-f1", "fixture reason", policy=experimental_policy,
            )
            self.assertEqual(document["profile_id"], "validation-analysis")
            self.assertNotEqual(
                document["activation_record_sha256"],
                policy_identity(load_public_activation_policy())["activation_record_sha256"],
            )
            # Comportamento central da decisão Astra: passando a política
            # correta, o mesmo validador que o público usa aceita o
            # documento experimental sem relaxar a validação estrutural.
            validate_document(document, policy=experimental_policy)
            promote_for_public_output(document, policy=experimental_policy)

    def test_experimental_identity_is_rejected_without_the_matching_policy(self):
        # A ativação pública padrão nunca é silenciosamente substituída: se
        # ninguém repassar a política experimental, o validador continua
        # comparando contra a política pública ativa e rejeita a
        # incompatibilidade — em vez de aceitar por engano.
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            from activation_policy import load_experimental_activation_policy

            experimental_policy = load_experimental_activation_policy(
                paths["activation"], profiles_path=paths["profiles"],
            )
            document = not_evaluable_document(
                "sample-f1", "run-f1", "fixture reason", policy=experimental_policy,
            )
            with self.assertRaisesRegex(ValueError, "policy identity"):
                validate_document(document)
            with self.assertRaisesRegex(ValueError, "policy identity"):
                promote_for_public_output(document)

    def test_export_evidence_cli_resolves_the_same_policy_run_sh_would_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            experimental_args = Namespace(
                experimental_activation_policy=str(paths["activation"]),
                activation_policy=None,
                profiles=str(paths["profiles"]),
            )
            policy = export_evidence._load_policy(experimental_args)
            self.assertEqual(policy["profile_id"], "validation-analysis")

            public_args = Namespace(experimental_activation_policy=None, activation_policy=None, profiles=None)
            self.assertIsNone(export_evidence._load_policy(public_args))

    def test_validate_run_artifacts_cli_resolves_the_same_policy_run_sh_would_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            experimental_args = Namespace(
                experimental_activation_policy=str(paths["activation"]),
                activation_policy=None,
                profiles=str(paths["profiles"]),
            )
            policy = validate_run_artifacts._load_policy(experimental_args)
            self.assertEqual(policy["profile_id"], "validation-analysis")

            public_args = Namespace(experimental_activation_policy=None, activation_policy=None, profiles=None)
            self.assertIsNone(validate_run_artifacts._load_policy(public_args))

    def test_finalize_run_cli_resolves_the_same_policy_run_sh_would_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            experimental_args = Namespace(
                experimental_activation_policy=str(paths["activation"]),
                activation_policy=None,
                profiles=str(paths["profiles"]),
            )
            policy = finalize_run._load_policy(experimental_args)
            self.assertEqual(policy["profile_id"], "validation-analysis")

            public_args = Namespace(experimental_activation_policy=None, activation_policy=None, profiles=None)
            self.assertIsNone(finalize_run._load_policy(public_args))

    def test_render_produces_a_report_for_a_not_evaluable_experimental_document(self):
        # export_evidence.render() é o passo que antes só executava para o
        # público; agora também precisa aceitar (sem reinterpretar) um
        # documento já validado com a identidade experimental.
        with tempfile.TemporaryDirectory() as tmp:
            paths = _experimental_fixture(Path(tmp))
            from activation_policy import load_experimental_activation_policy

            experimental_policy = load_experimental_activation_policy(
                paths["activation"], profiles_path=paths["profiles"],
            )
            document = not_evaluable_document(
                "sample-f1", "run-f1", "fixture reason", policy=experimental_policy,
            )
            report = export_evidence.render(document, validated=True)
            self.assertIn("sample-f1", report)
            self.assertIn("run-f1", report)


if __name__ == "__main__":
    unittest.main()
