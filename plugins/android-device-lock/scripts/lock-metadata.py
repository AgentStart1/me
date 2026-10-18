#!/usr/bin/env python3
"""Render lease templates and validate metadata without evaluating field values."""
import json
import sys
from pathlib import Path
from string import Template
def reject_constant(_):
    raise ValueError()
def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result
def validate(record):
    if not isinstance(record,dict): raise ValueError()
    if not isinstance(record.get("owner_token"),str) or not record["owner_token"]: raise ValueError()
    if type(record.get("expires_at_epoch")) is not int or record["expires_at_epoch"] < 0: raise ValueError()
    for key in ("project_dir","test_name","requested_at_utc","acquired_at_utc","host"):
        if not isinstance(record.get(key),str): raise ValueError()
    for key in ("adb_serial","lock_path"):
        if key in record and not isinstance(record[key],str): raise ValueError()
    for key in ("pid","max_timeout_seconds"):
        if type(record.get(key)) is not int or record[key] <= 0: raise ValueError()
    return record

def decode(source):
    return validate(json.loads(source,object_pairs_hook=unique_fields,parse_constant=reject_constant))

def render(values):
    template=Template(Path(__file__).with_name("lock.json.template").read_text(encoding="utf-8"))
    rendered=template.substitute({key:json.dumps(value,ensure_ascii=True) for key,value in values.items()})
    decode(rendered)
    print(rendered,end="")

def main():
    try:
        if sys.argv[1] == "render":
            keys=("project_dir","test_name","requested_at_utc","acquired_at_utc",
                  "max_timeout_seconds","expires_at_epoch","host","pid","adb_serial","lock_path","owner_token")
            values=dict(zip(keys,sys.argv[2:]))
            if len(sys.argv[2:]) != len(keys): raise ValueError()
            for key in ("max_timeout_seconds","expires_at_epoch","pid"):
                values[key]=int(values[key])
            render(values)
            raise SystemExit(0)
        record=decode(sys.stdin.read())
        if sys.argv[1] == "renew":
            duration,expiry,serial,lock_path=sys.argv[2:]
            record.update(max_timeout_seconds=int(duration),expires_at_epoch=int(expiry),
                          adb_serial=serial,lock_path=lock_path)
            render(record)
            raise SystemExit(0)
        kind,key=sys.argv[1:]
        if kind == "summary":
            print(json.dumps({k:record[k] for k in ("host","pid","test_name","expires_at_epoch") if k in record}))
        else:
            value=record.get(key)
            if (kind == "number" and type(value) is not int) or (kind == "string" and not isinstance(value,str)): raise ValueError()
            print(value,end="")
    except (ValueError,TypeError,KeyError,OSError):
        raise SystemExit(1)

if __name__ == "__main__":
    main()
