"""चाचणीसाठी बनावट Ollama server: embeddings = अक्षर-जोड्यांचे hash, chat = संदर्भ मिळाला की नाही ते सांगतो."""
import json, hashlib, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
def vec(t):
    v=[0.0]*256
    for i in range(len(t)-1):
        v[int(hashlib.md5(t[i:i+2].encode()).hexdigest(),16)%256]+=1
    return v
class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        b=json.dumps({"models":[{"name":"qwen2.5:7b"},{"name":"bge-m3:latest"}]}).encode()
        self.send_response(200);self.end_headers();self.wfile.write(b)
    def do_POST(self):
        d=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=="/api/embed":
            b=json.dumps({"embeddings":[vec(t) for t in d["input"]]}).encode()
            self.send_response(200);self.end_headers();self.wfile.write(b)
        else:
            last=d["messages"][-1]["content"]
            reply="संदर्भ मिळाला: "+last[:60].replace("\n"," ") if last.startswith("संदर्भ") else "सामान्य उत्तर"
            self.send_response(200);self.end_headers()
            for w in reply.split(" "):
                self.wfile.write((json.dumps({"message":{"content":w+" "},"done":False},ensure_ascii=False)+"\n").encode())
            self.wfile.write(b'{"done":true}\n')
ThreadingHTTPServer(("127.0.0.1",int(os.environ.get("MOCK_PORT","11434"))),H).serve_forever()
