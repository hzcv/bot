import time
import random
from instagrapi import Client
from instagrapi.exceptions import ChallengeRequired
from getpass import getpass

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

# ---------------- MAIN BOT ----------------
cl = Client()
owner_ids = []
no_abuse_list = []
locked_groups = {}
last_group_name_change = {}

def ask_credentials():
    username = input("Enter your Instagram username: ")
    password = getpass("Enter your Instagram password: ")
    return username, password

def handle_challenge(username):
    print("[*] Login triggered a challenge. Trying to send code to email...")
    try:
        cl.challenge_resolve(auto=True)
        code = input("[?] Enter the security code sent to your email: ").strip()
        cl.challenge_send_security_code(code)
    except Exception as e:
        print("[-] Failed to resolve challenge:", e)
        exit()

def login_flow():
    username, password = ask_credentials()
    try:
        cl.login(username, password)
    except ChallengeRequired:
        handle_challenge(username)
    except Exception as e:
        print("[-] Login failed:", e)
        exit()
    
    print(f"[+] Logged in as {username}")
    return cl.user_id_from_username(username)

def resolve_owner_ids():
    for uname in OWNER_USERNAMES:
        try:
            uid = cl.user_id_from_username(uname)
            owner_ids.append(uid)
            print(f"[+] Owner recognized: {uname} (ID: {uid})")
        except:
            print(f"[-] Failed to get user ID for owner '{uname}'")

def get_random_response(response_type, username=None):
    template = random.choice(RESPONSES[response_type])
    if username:
        return template.format(username=username)
    return template

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

def monitor_groups(self_id):
    print("[✓] Monitoring group chats...")
    replied_message_ids = {}

    while True:
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

                    if sender_id == self_id:
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

# ---------------- START ----------------
if _name_ == "_main_":
    print("""
    ███████╗██╗░░░██╗███████╗██████╗░  ░██████╗░██████╗░░█████╗░████████╗
    ██╔════╝██║░░░██║██╔════╝██╔══██╗  ██╔════╝░██╔══██╗██╔══██╗╚══██╔══╝
    █████╗░░╚██╗░██╔╝█████╗░░██████╔╝  ██║░░██╗░██████╔╝███████║░░░██║░░░
    ██╔══╝░░░╚████╔╝░██╔══╝░░██╔══██╗  ██║░░╚██╗██╔══██╗██╔══██║░░░██║░░░
    ███████╗░░╚██╔╝░░███████╗██║░░██║  ╚██████╔╝██║░░██║██║░░██║░░░██║░░░
    ╚══════╝░░░╚═╝░░░╚══════╝╚═╝░░╚═╝  ░╚═════╝░╚═╝░░╚═╝╚═╝░░╚═╝░░░╚═╝░░░
    """)
    self_user_id = login_flow()
    resolve_owner_ids()
    monitor_groups(self_user_id)
