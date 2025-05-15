from flask import Flask, render_template, request, jsonify
import time
import random
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired
from threading import Thread
import secrets

app = Flask(_name_)
app.secret_key = secrets.token_hex(16)

# ---------------- CONFIG ----------------
OWNER_USERNAMES = ["your_username"]  # Replace with your username
REPLY_DELAY = 2  # seconds
PREFIX = "!"  # Command prefix
GROUP_NAME_CHANGE_COOLDOWN = 3600  # 1 hour in seconds

# Response templates
RESPONSES = {
    "owner_greeting": [
        "Hey Boss! Your most welcome! How are you boss? I can help you!",
        "Namaste Owner Sahab! Aapka swagat hai! Kya haal chaal?",
        "Welcome back my creator! Kya service karu aapki?",
    ],
    "warning": [
        "Oye @{username} msg mat kar!",
        "Shanti se reh @{username}, warna teri maa chod dunga!",
        "Chup reh @{username}, warna group se uda dunga!",
    ],
    "funny": [
        "Abe @{username} chup hoja warna teri shaadi meri ex-se karwa dunga!",
        "@{username} teri acting dekh ke lagta hai tuition mein drama sikhaya tha!",
        "Abe @{username} itna mat bol, teri battery low ho jayegi!",
    ],
    "help": """
🤖 Bot Help Menu 🤖

{prefix}help - Show this help message
{prefix}owner - Show bot owner info
{prefix}pair - Get paired with a random group member
{prefix}groupname [new name] - Change group name (owner only)
{prefix}lock - Lock group (owner only)
{prefix}unlock - Unlock group (owner only)
{prefix}galimat [@user] - Don't abuse this user
{prefix}fun - Get a random fun message
""",
    "pairing": [
        "🔥 @{user1} aur @{user2} ki jodi bangayi! Shadi ka card bhejna mat bhoolna!",
        "💘 @{user1} + @{user2} = True Love! Ab bas shaadi kara do!",
        "👫 @{user1} aur @{user2} ko mila diya humne! Ab inhe rokoge kaise?",
    ],
    "no_abuse": [
        "Ok boss! @{username} ko gali nahi dunga!",
        "Samajh gaya malik! @{username} ka respect rakhunga!",
        "Haan haan @{username} ko kuch nahi bolunga!",
    ],
    "locked": "🔒 Group is locked! Only owner can change settings.",
    "unlocked": "🔓 Group is unlocked! Everyone can have fun now!",
}

# ---------------- GLOBALS ----------------
cl = None
bot_thread = None
running = False
owner_ids = []
no_abuse_list = []
locked_groups = {}
last_group_name_change = {}
self_user_id = None

# ---------------- HELPER FUNCTIONS ----------------
def get_random_response(response_type, username=None):
    template = random.choice(RESPONSES[response_type])
    if username:
        return template.format(username=username)
    return template

def handle_challenge(username):
    print("[*] Login triggered a challenge. Trying to send code to email...")
    try:
        cl.challenge_resolve(auto=True)
        code = input("[?] Enter the security code sent to your email: ").strip()
        cl.challenge_send_security_code(code)
    except Exception as e:
        print("[-] Failed to resolve challenge:", e)
        return False
    return True

def resolve_owner_ids():
    global owner_ids
    owner_ids = []
    for uname in OWNER_USERNAMES:
        try:
            uid = cl.user_id_from_username(uname)
            owner_ids.append(uid)
            print(f"[+] Owner recognized: {uname} (ID: {uid})")
        except:
            print(f"[-] Failed to get user ID for owner '{uname}'")

def process_command(command, sender_id, thread_id, thread_users):
    if not command.startswith(PREFIX):
        return False
    
    cmd = command[len(PREFIX):].split()[0].lower()
    args = command[len(PREFIX)+len(cmd):].strip()
    
    if cmd == "help":
        help_text = RESPONSES["help"].format(prefix=PREFIX)
        cl.direct_send(help_text, thread_ids=[thread_id])
        return True
    
    elif cmd == "owner":
        owners = ", ".join([f"@{uname}" for uname in OWNER_USERNAMES])
        cl.direct_send(f"🤖 Bot Owner: {owners}", thread_ids=[thread_id])
        return True
    
    elif cmd == "pair":
        if len(thread_users) < 2:
            cl.direct_send("Group mein kam se kam 2 log hone chahiye pairing ke liye!", thread_ids=[thread_id])
            return True
        
        user1 = random.choice(thread_users)
        user2 = random.choice(thread_users)
        while user2 == user1:
            user2 = random.choice(thread_users)
        
        user1_name = cl.user_info(user1).username
        user2_name = cl.user_info(user2).username
        
        pairing_msg = random.choice(RESPONSES["pairing"]).format(
            user1=user1_name, 
            user2=user2_name
        )
        cl.direct_send(pairing_msg, thread_ids=[thread_id])
        return True
    
    elif cmd == "groupname" and sender_id in owner_ids:
        if not args:
            cl.direct_send("Usage: !groupname [new name]", thread_ids=[thread_id])
            return True
        
        current_time = time.time()
        last_change = last_group_name_change.get(thread_id, 0)
        
        if current_time - last_change < GROUP_NAME_CHANGE_COOLDOWN:
            remaining = int(GROUP_NAME_CHANGE_COOLDOWN - (current_time - last_change))
            cl.direct_send(f"Wait {remaining} seconds before changing name again!", thread_ids=[thread_id])
            return True
        
        try:
            cl.direct_thread_title(thread_id, args)
            cl.direct_send(f"Group name changed to: {args}", thread_ids=[thread_id])
            last_group_name_change[thread_id] = current_time
        except Exception as e:
            cl.direct_send(f"Failed to change group name: {str(e)}", thread_ids=[thread_id])
        return True
    
    elif cmd == "lock" and sender_id in owner_ids:
        locked_groups[thread_id] = True
        cl.direct_send(RESPONSES["locked"], thread_ids=[thread_id])
        return True
    
    elif cmd == "unlock" and sender_id in owner_ids:
        locked_groups[thread_id] = False
        cl.direct_send(RESPONSES["unlocked"], thread_ids=[thread_id])
        return True
    
    elif cmd == "galimat" and sender_id in owner_ids:
        if not args.startswith("@"):
            cl.direct_send("Mention a user with @", thread_ids=[thread_id])
            return True
        
        username = args[1:].split()[0]
        try:
            user_id = cl.user_id_from_username(username)
            no_abuse_list.append(user_id)
            response = get_random_response("no_abuse", username)
            cl.direct_send(response, thread_ids=[thread_id])
        except:
            cl.direct_send(f"User @{username} not found", thread_ids=[thread_id])
        return True
    
    elif cmd == "fun":
        random_user = random.choice(thread_users)
        while random_user == sender_id:
            random_user = random.choice(thread_users)
        
        username = cl.user_info(random_user).username
        funny_msg = get_random_response("funny", username)
        cl.direct_send(funny_msg, thread_ids=[thread_id])
        return True
    
    return False

def bot_loop():
    global running, owner_ids, self_user_id
    print("[✓] Bot started monitoring group chats...")
    replied_message_ids = {}

    while running:
        try:
            threads = cl.direct_threads()
            for thread in threads:
                if len(thread.users) <= 1:
                    continue  # Skip if not a group

                thread_id = thread.id
                messages = cl.direct_messages(thread_id, amount=10)
                messages.reverse()

                for msg in messages:
                    sender_id = msg.user_id
                    msg_id = msg.id
                    text = msg.text or ""

                    if msg_id in replied_message_ids.get(thread_id, []):
                        continue

                    # Track that we processed this message
                    replied_message_ids.setdefault(thread_id, []).append(msg_id)

                    # Check if it's a command
                    if text.startswith(PREFIX):
                        if process_command(text, sender_id, thread_id, [u.pk for u in thread.users]):
                            continue

                    # Ignore messages from owners or self
                    if sender_id in owner_ids:
                        if random.random() < 0.3:  # 30% chance to greet owner
                            greeting = get_random_response("owner_greeting")
                            cl.direct_send(greeting, thread_ids=[thread_id])
                        continue

                    if sender_id == self_user_id:
                        continue

                    # Check if user is in no-abuse list
                    if sender_id in no_abuse_list:
                        continue

                    # Send warning or funny response
                    sender_username = cl.user_info(sender_id).username
                    
                    if random.random() < 0.7:  # 70% chance for warning
                        reply = get_random_response("warning", sender_username)
                    else:
                        reply = get_random_response("funny", sender_username)

                    cl.direct_send(reply, thread_ids=[thread_id])
                    print(f"[✓] Replied to @{sender_username} in thread {thread_id}")
                    time.sleep(REPLY_DELAY)

            time.sleep(5)
        except Exception as e:
            print(f"[-] Error: {str(e)}")
            time.sleep(10)
    
    print("[!] Bot stopped")

# ---------------- FLASK ROUTES ----------------
@app.route('/')
def index():
    status = "Running" if running else "Stopped"
    return render_template('index.html', status=status, owner_usernames=OWNER_USERNAMES)

@app.route('/login', methods=['POST'])
def login():
    global cl, running, bot_thread, self_user_id
    
    if running:
        return jsonify({"success": False, "message": "Bot is already running"})
    
    username = request.form.get('username')
    password = request.form.get('password')
    
    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"})
    
    try:
        cl = Client()
        cl.login(username, password)
        self_user_id = cl.user_id_from_username(username)
        resolve_owner_ids()
        
        running = True
        bot_thread = Thread(target=bot_loop)
        bot_thread.start()
        
        return jsonify({
            "success": True,
            "message": f"Logged in as {username} and bot started successfully"
        })
    except ChallengeRequired:
        if handle_challenge(username):
            try:
                cl.login(username, password)
                self_user_id = cl.user_id_from_username(username)
                resolve_owner_ids()
                
                running = True
                bot_thread = Thread(target=bot_loop)
                bot_thread.start()
                
                return jsonify({
                    "success": True,
                    "message": f"Logged in as {username} and bot started successfully"
                })
            except Exception as e:
                return jsonify({"success": False, "message": f"Login failed: {str(e)}"})
        else:
            return jsonify({"success": False, "message": "Challenge resolution failed"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Login failed: {str(e)}"})

@app.route('/logout', methods=['POST'])
def logout():
    global running, bot_thread, cl
    
    if not running:
        return jsonify({"success": False, "message": "Bot is not running"})
    
    running = False
    if bot_thread:
        bot_thread.join()
    
    if cl:
        try:
            cl.logout()
        except:
            pass
        cl = None
    
    return jsonify({"success": True, "message": "Bot stopped and logged out successfully"})

@app.route('/status')
def status():
    return jsonify({"running": running})

# ---------------- TEMPLATE ----------------
@app.route('/template')
def template():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Instagram Group Bot</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #405DE6;
            text-align: center;
        }
        .status {
            padding: 10px;
            text-align: center;
            margin: 20px 0;
            border-radius: 5px;
            font-weight: bold;
        }
        .running {
            background-color: #d4edda;
            color: #155724;
        }
        .stopped {
            background-color: #f8d7da;
            color: #721c24;
        }
        form {
            margin-top: 20px;
        }
        input, button {
            padding: 10px;
            margin: 5px 0;
            width: 100%;
            box-sizing: border-box;
        }
        button {
            background-color: #405DE6;
            color: white;
            border: none;
            cursor: pointer;
            border-radius: 5px;
        }
        button:hover {
            background-color: #3447b6;
        }
        .owner-list {
            margin: 20px 0;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Instagram Group Bot</h1>
        
        <div id="status" class="status"></div>
        
        <div class="owner-list">
            <h3>Bot Owners:</h3>
            <ul id="owner-list">
                {% for owner in owner_usernames %}
                    <li>@{{ owner }}</li>
                {% endfor %}
            </ul>
        </div>
        
        <div id="login-form">
            <h3>Login to Start Bot</h3>
            <form onsubmit="event.preventDefault(); login();">
                <input type="text" id="username" placeholder="Instagram Username" required>
                <input type="password" id="password" placeholder="Instagram Password" required>
                <button type="submit">Login & Start Bot</button>
            </form>
        </div>
        
        <div id="logout-form" style="display: none;">
            <form onsubmit="event.preventDefault(); logout();">
                <button type="submit">Stop Bot & Logout</button>
            <p id="bot-message"></p>
        </div>
    </div>

    <script>
        function updateStatus() {
            fetch('/status')
                .then(response => response.json())
                .then(data => {
                    const statusDiv = document.getElementById('status');
                    if (data.running) {
                        statusDiv.textContent = 'Status: Running';
                        statusDiv.className = 'status running';
                        document.getElementById('login-form').style.display = 'none';
                        document.getElementById('logout-form').style.display = 'block';
                    } else {
                        statusDiv.textContent = 'Status: Stopped';
                        statusDiv.className = 'status stopped';
                        document.getElementById('login-form').style.display = 'block';
                        document.getElementById('logout-form').style.display = 'none';
                    }
                });
        }
        
        function login() {
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('bot-message').textContent = data.message;
                if (data.success) {
                    updateStatus();
                } else {
                    alert(data.message);
                }
            });
        }
        
        function logout() {
            fetch('/logout', {
                method: 'POST'
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('bot-message').textContent = data.message;
                updateStatus();
            });
        }
        
        // Initial status check
        updateStatus();
    </script>
</body>
</html>
"""

if _name_ == '_main_':
    app.run(debug=True)
