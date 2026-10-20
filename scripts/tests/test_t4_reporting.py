import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_fasta(path, records):
    path.write_text(''.join(f'>{name}\n{seq}\n' for name, seq in records.items()), encoding='utf-8')


def tsv_rows(path):
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle, delimiter='\t'))


def shell_path(path):
    if os.environ.get('BASH') and sys.platform == 'win32':
        cygpath = Path(os.environ['BASH']).parent.parent / 'usr' / 'bin' / 'cygpath.exe'
        return subprocess.run([str(cygpath), '-u', str(path)], capture_output=True, text=True, check=True).stdout.strip()
    return str(path)


class T4ReportingTests(unittest.TestCase):
    def test_evidence_details_show_units_alignment_metrics_and_unmeasured_states(self):
        sys.path.insert(0,str(ROOT/'scripts/evidence'))
        from report_details import render_details
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)
            def table(name,fields,rows):
                with (base/name).open('w',encoding='utf-8',newline='') as handle:
                    writer=csv.DictWriter(handle,fieldnames=fields,delimiter='\t',lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
            table('fragment_evidence.tsv',['qseqid','sseqid','task','query_covered_bp','qlen','sequence_sha256','assembly_method'],[dict(qseqid='q1',sseqid='refA',task='blastn',query_covered_bp=20,qlen=50,sequence_sha256='abc',assembly_method='spades')])
            table('locus_evidence.tsv',['locus_id','task'],[dict(locus_id='L1',task='blastn')])
            table('hsp_evidence.tsv',['locus_id','qseqid','eligible','rejection_reason','bitscore','identity_pct','alignment_length'],[dict(locus_id='L1',qseqid='q1',eligible='true',rejection_reason='',bitscore=50,identity_pct=95,alignment_length=20),dict(locus_id='L1',qseqid='q1',eligible='false',rejection_reason='LOW_BITSCORE',bitscore=2,identity_pct=70,alignment_length=5)])
            table('read_support.tsv',['support_status'],[dict(support_status='NOT_EVALUATED')])
            table('coverage.tsv',['breadth_1x'],[])
            candidate=dict(locus_id='L1',query_ids=['q1'],reference_id='refA',candidate_class='EXPLORATORY_FRAGMENT',specificity_status='AMBIGUOUS',support={'status':'NOT_EVALUATED'},coverage={'status':'NOT_EVALUATED'},assembly_support={'status':'NOT_EVALUATED'})
            report=render_details(base,dict(candidates=[candidate]))
            self.assertIn('IDs de contigs/query recuperados em alinhamentos | 1',report)
            self.assertIn('Sequências distintas | 1',report)
            self.assertIn('Loci | 1',report)
            self.assertIn('Accessions de referência | 1',report)
            self.assertIn('| 95 | 20 | 20/50 | 0.400 | AMBIGUOUS | NOT_EVALUATED | NOT_EVALUATED | NOT_EVALUATED |',report)
            self.assertIn('`LOW_BITSCORE`: 1',report)

    def test_classic_report_separates_hsps_contigs_accessions_and_assembler(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); assembly=base/'data/assemblies/T4CHECK_assembly'; assembly.mkdir(parents=True)
            write_fasta(assembly/'contigs.fa', {'qstrong':'A'*100,'qreview':'C'*50,'nohit':'G'*30})
            (assembly/'assembly_metadata.env').write_text('ASSEMBLER_REQUESTED="velvet"\nASSEMBLER_USED="spades"\nASSEMBLY_FALLBACK=1\nASSEMBLY_FAILURE_TYPE="HARD"\n',encoding='utf-8')
            blast=base/'input.tsv'
            rows=[]
            for q,ref,pident,length,qlen,evalue,score in [('qstrong','refA',95,100,100,'1e-20',100),('qreview','refB',70,25,50,'1e-3',25),('qstrong','refC',90,80,100,'1e-10',80)]:
                mismatch=int(length*(100-pident)/100)
                rows.append('\t'.join(map(str,[q,ref,pident,length,mismatch,0,1,length,1,length,evalue,score,qlen,500,length-mismatch,0])))
            blast.write_text('\n'.join(rows)+'\n',encoding='utf-8')
            report=base/'results/reports/T4CHECK_summary.md'
            result=subprocess.run([
                os.environ.get('BASH', 'bash'), '-lc',
                'bash "$1" --sample "$2" --contigs "$3" --blast "$4" --out "$5"',
                't4-test', shell_path(ROOT/'scripts/pipeline/report_minimal.sh'), 'T4CHECK',
                shell_path(assembly/'contigs.fa'), shell_path(blast), shell_path(report),
            ],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+'\n'+result.stdout)
            text=report.read_text(encoding='utf-8')
            self.assertIn('Montador utilizado: spades',text)
            self.assertIn('HSPs/alinhamentos tabulares: 3',text)
            self.assertIn('Accessions atingidos | 3',text)
            self.assertIn('Contigs exportados | 2',text)
            self.assertIn('Pendentes por sequência ausente | 0',text)
            self.assertIn('Seleção final para interpretação:** não executada',text)
            ledger=base/'results/blast/T4CHECK_selection_ledger.tsv'
            self.assertTrue(ledger.is_file())
            dispositions={row['qseqid']:row['disposition'] for row in tsv_rows(ledger)}
            self.assertEqual(dispositions['nohit'],'NO_BLAST_HIT')

    def test_class_and_length_filters_keep_every_query_in_selection_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            fasta = base / 'contigs.fa'
            write_fasta(fasta, {
                'keep': 'A' * 50,
                'class_excluded': 'C' * 50,
                'length_excluded': 'G' * 20,
                'no_hit': 'T' * 42,
            })
            labeled = base / 'labeled.tsv'
            fields = ['qseqid','sseqid','pident','length','evalue','bitscore','qlen','aln_cov','adj_identity','evidence_class','risk_note']
            with labeled.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t', lineterminator='\n')
                writer.writeheader()
                for qid, klass, size in [('keep','STRONG',50),('class_excluded','REVIEW',50),('length_excluded','STRONG',20),('missing','STRONG',60)]:
                    writer.writerow(dict(qseqid=qid,sseqid='refA',pident=95,length=size,evalue='1e-20',bitscore=90,qlen=size,aln_cov=1,adj_identity=95,evidence_class=klass,risk_note=''))
            out = base / 'blast'
            result = subprocess.run([sys.executable, str(ROOT/'scripts/pipeline/export_hit_contigs.py'), '--labeled', str(labeled), '--contigs', str(fasta), '--sample', 't4sample', '--out-dir', str(out), '--classes', 'STRONG', '--min-len', '40'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = tsv_rows(out/'t4sample_selection_ledger.tsv')
            by_id = {row['qseqid']: row for row in rows}
            self.assertEqual({k:v['disposition'] for k,v in by_id.items()}, {
                'keep':'EXPORTED', 'class_excluded':'EXCLUDED_CLASS_FILTER',
                'length_excluded':'EXCLUDED_LENGTH_FILTER', 'no_hit':'NO_BLAST_HIT',
                'missing':'PENDING_MISSING_CONTIG',
            })
            summary = json.loads((out/'t4sample_selection_summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['counts_by_disposition']['EXPORTED'], 1)
            self.assertEqual(summary['counts_by_disposition']['EXCLUDED_CLASS_FILTER'], 1)
            self.assertEqual(summary['counts_by_disposition']['EXCLUDED_LENGTH_FILTER'], 1)
            self.assertEqual(summary['counts_by_disposition']['PENDING_MISSING_CONTIG'], 1)
            self.assertEqual(summary['counts_by_disposition']['NO_BLAST_HIT'], 1)
            self.assertTrue((out/'t4sample_hit_contigs.fa').read_text().startswith('>keep '))

    def test_read_rescue_ledger_records_acceptance_rejection_and_best_hit_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); raw=base/'raw.tsv'; out=base/'reads.tsv'
            def row(q, ref, pid, length, ev, score, qlen):
                values=[q,ref,str(pid),str(length),'0','0','1',str(length),'1',str(length),str(ev),str(score),str(qlen),'1000']
                return '\t'.join(values)
            raw.write_text('\n'.join([
                row('good','refA',95,100,'1e-20',110,100),
                row('good','refB',95,100,'1e-20',90,100),
                row('badpid','refA',80,100,'1e-20',120,100),
                row('badev','refA',95,100,'1e-2',120,100),
                row('shortfail','refA',95,20,'1e-20',120,150),
                row('shortpass','refA',95,20,'1e-20',120,20),
            ])+'\n',encoding='utf-8')
            result=subprocess.run([sys.executable,str(ROOT/'scripts/pipeline/filter_rescue_reads.py'),'--blast-raw',str(raw),'--out-tsv',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            candidates=tsv_rows(out)
            self.assertEqual({row['qseqid'] for row in candidates},{'good','shortpass'})
            decisions=tsv_rows(out.with_suffix(out.suffix+'.decisions.tsv'))
            disposition={(row['qseqid'],row['sseqid']):row['disposition'] for row in decisions}
            self.assertEqual(disposition[('good','refA')],'SELECTED_BEST_HIT')
            self.assertEqual(disposition[('good','refB')],'ACCEPTED_ALTERNATIVE_NOT_SELECTED')
            self.assertEqual(disposition[('badpid','refA')],'REJECTED_FILTER')
            self.assertEqual(disposition[('badev','refA')],'REJECTED_FILTER')
            self.assertEqual(disposition[('shortfail','refA')],'REJECTED_FILTER')
            self.assertEqual(disposition[('shortpass','refA')],'SELECTED_BEST_HIT')
            provenance=json.loads(out.with_suffix(out.suffix+'.provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(provenance['candidate_count'],2)
            self.assertEqual(provenance['input_alignment_rows'],6)


if __name__ == '__main__':
    unittest.main()
