"""Command line entry point: `fleet <command>`."""

from __future__ import annotations

import argparse
import json
import logging

from fleet.config import ROOT

CONTRACT_PATH = ROOT / "contracts" / "telemetry_event.schema.json"


def _contract() -> str:
    from fleet.schemas import TelemetryEvent

    return json.dumps(TelemetryEvent.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fleet")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download and verify the NASA C-MAPSS archive")
    sub.add_parser("train", help="train and evaluate the RUL model, save it to artifacts/")
    sub.add_parser("init", help="create the database schema and Kafka topics")
    p = sub.add_parser("produce", help="replay test engines into Kafka")
    p.add_argument("--ticks-per-second", type=float, default=None)
    sub.add_parser("score", help="run the scoring consumer")
    sub.add_parser("contract", help="write the telemetry JSON Schema to contracts/")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "fetch":
        from fleet.data import fetch

        fetch()
    elif args.cmd == "train":
        from fleet import model
        from fleet.data import read_split, read_test_rul

        m = model.train(read_split("train"))
        metrics = model.evaluate(m, read_split("test"), read_test_rul())
        model.save(m, metrics)
        print(json.dumps(metrics))
    elif args.cmd == "init":
        from fleet import db
        from fleet.producer import create_topics

        with db.connect() as conn:
            db.init_schema(conn)
        create_topics()
    elif args.cmd == "produce":
        from fleet.producer import run

        run(args.ticks_per_second)
    elif args.cmd == "score":
        from fleet.scorer import run

        run()
    elif args.cmd == "contract":
        CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTRACT_PATH.write_text(_contract(), encoding="utf-8")
        print(f"wrote {CONTRACT_PATH}")


if __name__ == "__main__":
    main()
