from scripts.dashboard.jobs import classify_evidence_failure


def test_signal_failure_is_not_invalid_input():
    assert classify_evidence_failure(['FASTQ validated', '[FATAL] process killed'], 137) == 'PROCESS_KILLED'
    assert classify_evidence_failure(['FASTQ validated', '[FATAL] process killed'], -9) == 'PROCESS_KILLED'
    assert classify_evidence_failure(['FASTQ validated', '[FATAL] tool failed'], 1) == 'TOOL_FAILURE'
    assert classify_evidence_failure(['[FATAL] FASTQ invalid'], 1) == 'INPUT_INVALID'


def test_success_assembly_inputs_and_outputs_not_rewritten():
    # Error classification accepts lines as evidence and must not mutate that evidence.
    lines = ['FASTQ validated', '[FATAL] process killed']
    before = '\n'.join(lines).encode()
    classify_evidence_failure(lines, 137)
    assert '\n'.join(lines).encode() == before
