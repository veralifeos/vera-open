"""Feedback loop orchestrator — coleta → tracker → patterns → writer."""

from vera.feedback.collector import ObservationCollector
from vera.feedback.patterns import PatternEngine
from vera.feedback.tracker import BehaviorTracker
from vera.feedback.writer import UserProfileWriter


def run_feedback_loop() -> dict:
    """Executa o loop completo de feedback.

    Returns:
        dict com keys: inferences_added, inferences_removed, total_active,
                       signals_detected, observations_analyzed
    """
    print("   VERA — Feedback Loop")
    print("=" * 40)

    # 1. Load observations
    print("   Carregando observações...")
    try:
        collector = ObservationCollector()
        observations = collector.load_observations()
    except FileNotFoundError:
        observations = []

    print(f"   {len(observations)} observações encontradas")

    if not observations:
        print("   Sem observações. Execute pelo menos 5 briefings antes.")
        return {
            "inferences_added": 0,
            "inferences_removed": 0,
            "total_active": 0,
            "signals_detected": 0,
            "observations_analyzed": 0,
        }

    # 2. Detect behavioral signals
    print("\n   Detectando sinais comportamentais...")
    tracker = BehaviorTracker()
    signals = tracker.detect_signals(observations)
    print(f"   {len(signals)} sinal(is) detectado(s)")

    for s in signals:
        print(f"     [{s.type}] confidence={s.confidence:.2f}, evidence={s.evidence_count}")

    # 3. Generate inferences
    print("\n   Gerando inferências...")
    engine = PatternEngine()
    inferences = engine.generate_inferences(signals)
    print(f"   {len(inferences)} inferência(s) gerada(s)")

    # 4. Write to USER.md
    print("\n   Atualizando USER.md...")
    writer = UserProfileWriter()
    result = writer.update(inferences)
    print(f"   Adicionadas: {result['added']} | Removidas: {result['removed']} | Total: {result['total']}")

    print("\n   FEEDBACK LOOP FINALIZADO!")
    return {
        "inferences_added": result["added"],
        "inferences_removed": result["removed"],
        "total_active": result["total"],
        "signals_detected": len(signals),
        "observations_analyzed": len(observations),
    }
