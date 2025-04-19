import subprocess

result = subprocess.run(["containerlab", "version"], capture_output=True)

dir(result)
print(result)

print(result.stdout.decode("utf-8"))
