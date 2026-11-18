# Test cases for rules.yml (semgrep scan --test .semgrep). Never imported or executed.
# ruff: noqa
import os
import pickle
import subprocess

import httpx
import jwt
import yaml
from sqlalchemy import text

# ruleid: pap-subprocess-shell
subprocess.run("ls " + name, shell=True)
# ruleid: pap-subprocess-shell
subprocess.Popen(cmd, shell=flag)
# ok: pap-subprocess-shell
subprocess.Popen(argv, shell=False)
# ok: pap-subprocess-shell
subprocess.run(["openmhs", "--version"], check=True)

# ruleid: pap-os-system
os.system("rm " + path)

# ruleid: pap-eval-exec
eval(user_input)

# ruleid: pap-sql-text-interpolation
session.execute(text(f"select * from jobs where id = '{job_id}'"))
# ruleid: pap-sql-text-interpolation
session.execute(text("select * from jobs where id = '%s'" % job_id))
# ok: pap-sql-text-interpolation
session.execute(text("select * from jobs where id = :id"), {"id": job_id})

# ruleid: pap-unsafe-deserialization
pickle.loads(blob)
# ruleid: pap-unsafe-deserialization
yaml.load(doc)

# ruleid: pap-jwt-unverified
jwt.decode(token, options={"verify_signature": False})
# ok: pap-jwt-unverified
jwt.decode(token, key, algorithms=["RS256"], audience=aud, issuer=iss)

# ruleid: pap-tls-verify-disabled
httpx.get(url, verify=False)
