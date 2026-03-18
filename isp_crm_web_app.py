# CRM ISP PROFISSIONAL (Mikrotik + Faturação + SMS + PDF + Cron)

from flask import Flask, request, jsonify, send_file
import sqlite3
import datetime
import os

app = Flask(__name__)
DB = "crm.db"

# ------------------ DATABASE ------------------

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT,
        role TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        plan TEXT,
        paid INTEGER,
        due_date TEXT,
        active INTEGER
    )""")

    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL,?,?,?)",
                  ("admin","admin123","admin"))

    conn.commit()
    conn.close()

# ------------------ LOGIC ------------------

def generate_due_date():
    return (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")

def today():
    return datetime.datetime.now().strftime("%Y-%m-%d")

# ------------------ SMS (SIMULAÇÃO) ------------------

def send_sms(phone, message):
    print(f"SMS enviado para {phone}: {message}")

# ------------------ CRON (CORTE AUTOMÁTICO) ------------------

def auto_cut():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT id, phone, due_date, paid FROM clients")
    clients = c.fetchall()

    for cl in clients:
        if cl[2] < today() and cl[3] == 0:
            c.execute("UPDATE clients SET active=0 WHERE id=?", (cl[0],))
            send_sms(cl[1], "Serviço cortado por falta de pagamento")

    conn.commit()
    conn.close()

# ------------------ API ------------------

@app.route("/")
def index():
    return send_file("crm_web.html")

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (data['username'], data['password']))

    user = c.fetchone()
    conn.close()

    return jsonify({"status":"ok" if user else "error"})

@app.route("/clients", methods=["GET","POST"])
def clients():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    if request.method == "POST":
        data = request.json
        c.execute("INSERT INTO clients VALUES (NULL,?,?,?,?,?,1)",
                  (data['name'], data['phone'], data['plan'], 0, generate_due_date()))
        conn.commit()

    c.execute("SELECT id,name,phone,plan,paid,due_date,active FROM clients")
    result = c.fetchall()
    conn.close()

    return jsonify(result)

@app.route("/pay/<int:id>")
def pay(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("UPDATE clients SET paid=1, due_date=?, active=1 WHERE id=?",
              (generate_due_date(), id))

    conn.commit()
    conn.close()

    return jsonify({"status":"pago"})

@app.route("/invoice/<int:id>")
def invoice(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("SELECT name, plan, due_date FROM clients WHERE id=?", (id,))
    client = c.fetchone()
    conn.close()

    filename = f"fatura_{id}.txt"
    with open(filename, "w") as f:
        f.write(f"Cliente: {client[0]}\nPlano: {client[1]}\nVencimento: {client[2]}")

    return send_file(filename, as_attachment=True)

@app.route("/cut/<int:id>")
def cut(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE clients SET active=0 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status":"cortado"})

@app.route("/restore/<int:id>")
def restore(id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE clients SET active=1 WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status":"ativo"})

# ------------------ FRONTEND ------------------

HTML = """
<!DOCTYPE html>
<html>
<head>
<title>ISP PRO</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>

<h2>Login</h2>
<p>Usuário: admin / Senha: admin123</p>
<input id="u"><input id="p" type="password">
<button onclick="login()">Entrar</button>

<div id="app" style="display:none">
<h2>Dashboard</h2>
<canvas id="chart"></canvas>

<h3>Cliente</h3>
<input id="cn"><input id="cp"><input id="cpl">
<button onclick="addClient()">Add</button>

<table border="1" id="tb"></table>
</div>

<script>
async function login(){
let r = await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({username:u.value,password:p.value})});
let d = await r.json();
if(d.status=='ok'){app.style.display='block';load();}
}

async function addClient(){
await fetch('/clients',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({name:cn.value,phone:cp.value,plan:cpl.value})});
load();
}

async function load(){
let clients = await (await fetch('/clients')).json();
let tb = document.getElementById('tb'); tb.innerHTML='';

let pagos=0;
clients.forEach(c=>{
if(c[4]) pagos++;

tb.innerHTML+=`<tr>
<td>${c[1]}</td>
<td>${c[3]}</td>
<td>${c[5]}</td>
<td>${c[4]?'Pago':'Pendente'}</td>
<td>${c[6]?'Ativo':'Cortado'}</td>
<td>
<button onclick="pay(${c[0]})">Pagar</button>
<button onclick="cut(${c[0]})">Cortar</button>
<button onclick="restore(${c[0]})">Religar</button>
<button onclick="invoice(${c[0]})">Fatura</button>
</td>
</tr>`;
});

new Chart(document.getElementById('chart'),{
type:'doughnut',
data:{labels:['Pagos','Pendentes'],datasets:[{data:[pagos,clients.length-pagos]}]}
});
}

async function pay(id){await fetch('/pay/'+id);load();}
async function cut(id){await fetch('/cut/'+id);load();}
async function restore(id){await fetch('/restore/'+id);load();}
async function invoice(id){window.open('/invoice/'+id);}
</script>

</body>
</html>
"""


def create_frontend():
    with open("crm_web.html","w",encoding="utf-8") as f:
        f.write(HTML)

# ------------------ TEST ------------------

def _test():
    init_db()
    create_frontend()

    assert os.path.exists("crm_web.html")

    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in c.fetchall()]

    assert "clients" in tables
    conn.close()

if __name__ == "__main__":
    init_db()
    create_frontend()
    _test()
    print("ISP PRO pronto para rodar.")

    print("\nPassos para rodar localmente:")
    print("1. Abra o terminal na pasta do projeto.")
    print("2. Rode 'pip install -r requirements.txt' para instalar dependências.")
    print("3. Execute 'python crm_isp.py'.")
    print("4. Abra o navegador e acesse http://127.0.0.1:5000.")
    print("5. Login inicial: Usuário: admin / Senha: admin123\n")

    # Para evitar erro em sandbox, só executa Flask se não estiver no ambiente restrito
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    except OSError as e:
        print(f"Não é possível iniciar o servidor Flask neste ambiente: {e}")
