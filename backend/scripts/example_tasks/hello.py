import os
import sys

print("hello", os.environ.get("TASK_PARAM_NAME", "unknown"))
print("args", sys.argv[1:])
