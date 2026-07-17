# -*- coding: utf-8 -*-
"""
WorkBuddy 积分叠加注入器 (纯标准库)
====================================
前提：WorkBuddy 带 --remote-debugging-port=9222 运行
用法：
  python inject_credits.py                    # 注入（默认叠加值在下方配置）
  python inject_credits.py --watch            # 持续监控
  python inject_credits.py --value 50000      # 叠加 50000
  python inject_credits.py --edition free     # 版本设为 free

特点：
  - 叠加模式：显示值 = 真实积分 + 注入值
  - 支持运行中改值重跑：每次执行重新 hook，用最新 ADD 值
  - 不需要重启 WorkBuddy 即可改注入值
"""
import socket, struct, base64, os, json, time, sys, urllib.request

CDP_URL = "http://127.0.0.1:9222"
ADD_LEFT = "20000"
ADD_TOTAL = "20000"
NEW_EDITION = "pro"
NEW_ISPRO = True
WATCH_INTERVAL = 30


# ==================== WebSocket ====================
def ws_connect(url):
    rest = url[5:]; slash = rest.find('/')
    host_port = rest[:slash]; path = rest[slash:]
    if ':' in host_port: host, port = host_port.rsplit(':', 1); port = int(port)
    else: host, port = host_port, 80
    sock = socket.create_connection((host, port), timeout=15)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall(("GET " + path + " HTTP/1.1\r\nHost: " + host_port + "\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: " + key + "\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        c = sock.recv(4096)
        if not c: raise Exception("handshake closed")
        resp += c
    if b'101' not in resp.split(b'\r\n')[0]: raise Exception("handshake failed")
    return sock

def ws_send(sock, data):
    payload = data.encode('utf-8')
    mask_key = os.urandom(4)
    header = bytearray([0x81])
    length = len(payload)
    if length < 126: header.append(0x80 | length)
    elif length < 65536: header.append(0x80 | 126); header += struct.pack('>H', length)
    else: header.append(0x80 | 127); header += struct.pack('>Q', length)
    header += mask_key
    masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + bytes(masked))

def ws_recv(sock):
    hdr = sock.recv(2)
    if len(hdr) < 2: return None
    opcode = hdr[0] & 0x0F; masked = (hdr[1] & 0x80) != 0; length = hdr[1] & 0x7F
    if length == 126: length = struct.unpack('>H', sock.recv(2))[0]
    elif length == 127: length = struct.unpack('>Q', sock.recv(8))[0]
    if masked: mask_key = sock.recv(4)
    data = b''
    while len(data) < length:
        c = sock.recv(length - len(data))
        if not c: break
        data += c
    if masked: data = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(data))
    if opcode == 8: return None
    if opcode == 9: return ws_recv(sock)
    return data.decode('utf-8', 'ignore')

def eval_js(sock, js, msg_id=1, timeout=30):
    ws_send(sock, json.dumps({"id": msg_id, "method": "Runtime.evaluate",
        "params": {"expression": js, "returnByValue": True, "awaitPromise": True}}))
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = ws_recv(sock)
        if frame is None: return None
        try:
            d = json.loads(frame)
            if d.get('id') == msg_id:
                if 'result' in d and 'result' in d['result']:
                    return d['result']['result'].get('value')
                return json.dumps(d, ensure_ascii=False)[:500]
        except: pass
    return None


# ==================== CDP ====================
def get_tabs():
    try:
        return json.loads(urllib.request.urlopen(CDP_URL + "/json", timeout=5).read().decode())
    except: return None

def find_tab(tabs):
    if not tabs: return None
    for t in tabs:
        if t.get('type') == 'page': return t
    return tabs[0]


# ==================== 注入逻辑 ====================
# 关键设计：
#   1. adapter hook：如果之前 hook 过（有 __orig），先恢复原方法，再装新 hook
#      这样每次运行都用最新的 ADD 值
#   2. state patch：记录原始真实值到 __realLeft/__realTotal
#      每次运行：显示值 = 原始值 + 当前ADD（覆盖式，不累加）
#   3. resources 同理
JS_INJECT = r"""
(function(ADD_LEFT, ADD_TOTAL, NEW_EDITION, NEW_ISPRO){
    function parseNum(s){var n=parseFloat(s);return isNaN(n)?0:n}
    function toStr(n){return String(n)}
    var addLeft = parseNum(ADD_LEFT);
    var addTotal = parseNum(ADD_TOTAL);

    function mergeUsage(real){
        var base = real && typeof real === 'object' ? Object.assign({}, real) : {};
        var realLeft = parseNum(base.usageLeft);
        var realTotal = parseNum(base.usageTotal);
        base.usageLeft = toStr(realLeft + addLeft);
        base.usageTotal = toStr(realTotal + addTotal);
        if(NEW_ISPRO && base.isPro !== undefined) base.isPro = true;
        if(base.editionType !== undefined) base.editionType = NEW_EDITION;
        base.refreshAt = Date.now() + 365*864e5;
        if(Array.isArray(base.resources)){
            base.resources.forEach(function(r){
                if(r && r.left !== undefined){
                    var rl = parseNum(r.left);
                    var rt = parseNum(r.total);
                    r.left = rl + addLeft;
                    r.total = rt + addTotal;
                }
            });
        }
        console.log('[INJECT] real=' + realLeft + ' + ' + addLeft + ' = ' + base.usageLeft);
        return base;
    }

    var root = document.getElementById('root');
    if(!root) return 'no root';
    var ck = Object.keys(root).find(function(k){return k.startsWith('__reactContainer')});
    if(!ck) return 'no container';
    var fr = root[ck].stateNode || root[ck];
    var hr = fr.current || fr;
    if(!hr) return 'no fiber';

    var ah=0, ph=0, sp=0, sf=0;
    var seen = new Set(); var q=[hr]; var visited=0;
    var processed = new Set();
    while(q.length && visited<1e5){
        var f=q.shift(); visited++;
        if(!f||seen.has(f))continue; seen.add(f);
        var p=f.memoizedProps;
        if(p&&typeof p==='object'){
            Object.keys(p).forEach(function(k){
                var v=p[k];
                if(v&&typeof v==='object'&&typeof v.getAccountUsage==='function'&&!processed.has(v)){
                    processed.add(v);
                    // 恢复原始方法（如果之前 hook 过）
                    if(v.__origGetAccountUsage){
                        v.getAccountUsage = v.__origGetAccountUsage;
                    } else {
                        v.__origGetAccountUsage = v.getAccountUsage;
                    }
                    // 装新 hook（闭包捕获当前 addLeft/addTotal）
                    v.getAccountUsage = async function(){
                        var real = null;
                        try { real = await v.__origGetAccountUsage(); } catch(e) {}
                        return mergeUsage(real);
                    };
                    ah++;
                }
            });
            // backendProvider.api.authGetAccountUsage 同理
            if(p.backendProvider&&p.backendProvider.api&&typeof p.backendProvider.api.authGetAccountUsage==='function'){
                var a=p.backendProvider.api;
                if(!processed.has(a)){
                    processed.add(a);
                    if(a.__origAuth){
                        a.authGetAccountUsage = a.__origAuth;
                    } else {
                        a.__origAuth = a.authGetAccountUsage;
                    }
                    a.authGetAccountUsage = async function(){
                        var real = null;
                        try { real = await a.__origAuth(); } catch(e) {}
                        return mergeUsage(real);
                    };
                    ph++;
                }
            }
        }
        // state patch: 基于原始值重算（支持改 ADD 值重跑）
        var st=f.memoizedState;
        while(st){
            var m=st.memoizedState;
            if(m&&typeof m==='object'&&m.usageLeft!==undefined){
                // 首次：记录原始值；后续：用原始值重算
                if(m.__realLeft === undefined){
                    m.__realLeft = parseNum(m.usageLeft);
                    m.__realTotal = parseNum(m.usageTotal);
                }
                m.usageLeft = toStr(m.__realLeft + addLeft);
                m.usageTotal = toStr(m.__realTotal + addTotal);
                m.usageUsed = "0";
                if(NEW_ISPRO&&m.isPro!==undefined)m.isPro=true;
                if(m.editionType!==undefined)m.editionType=NEW_EDITION;
                if(Array.isArray(m.resources)){
                    m.resources.forEach(function(r){
                        if(r && r.left !== undefined){
                            if(r.__realLeft === undefined){
                                r.__realLeft = parseNum(r.left);
                                r.__realTotal = parseNum(r.total);
                            }
                            r.left = r.__realLeft + addLeft;
                            r.total = r.__realTotal + addTotal;
                        }
                    });
                }
                sp++;
                if(f.stateNode&&typeof f.stateNode.forceUpdate==='function'){try{f.stateNode.forceUpdate();sf++}catch(e){}}
                if(st.queue&&typeof st.queue.dispatch==='function'){try{st.queue.dispatch(Object.assign({},m));sf++}catch(e){}}
            }
            st=st.next;
        }
        if(f.child)q.push(f.child);
        if(f.sibling)q.push(f.sibling);
    }
    return 'adapters='+ah+' apis='+ph+' state='+sp+' forced='+sf+' addLeft='+addLeft;
})({L},{T},{E},{P});
"""

def inject(add_left=None, add_total=None, edition=None, is_pro=None):
    """注入积分到 WorkBuddy

    Args:
        add_left: 叠加剩余积分，None 用默认 ADD_LEFT
        add_total: 叠加总积分，None 用默认 ADD_TOTAL
        edition: 版本类型 (pro/free)，None 用默认 NEW_EDITION
        is_pro: 是否 Pro，None 用默认 NEW_ISPRO

    Returns:
        bool: 注入是否成功
    """
    al = str(add_left) if add_left is not None else ADD_LEFT
    at = str(add_total) if add_total is not None else ADD_TOTAL
    ed = edition if edition is not None else NEW_EDITION
    ip = is_pro if is_pro is not None else NEW_ISPRO

    tabs = get_tabs()
    if not tabs:
        import logging
        logging.getLogger(__name__).warning("[inject] CDP 调试端口未开，无法获取 tabs")
        return False
    tab = find_tab(tabs)
    if not tab:
        import logging
        logging.getLogger(__name__).warning("[inject] 没有可用的 page tab")
        return False
    try:
        sock = ws_connect(tab['webSocketDebuggerUrl'])
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[inject] WebSocket 连接失败: {e}")
        return False
    try:
        js = JS_INJECT.replace("{L}", json.dumps(al)).replace("{T}", json.dumps(at)).replace("{E}", json.dumps(ed)).replace("{P}", json.dumps(ip))
        r = eval_js(sock, js, 1)
        import logging
        logging.getLogger(__name__).info(f"[inject] 注入结果: add_left={al}, add_total={at}, response={r}")
        return r is not None
    finally:
        sock.close()


def inject_credits_to_workbuddy(credits: float):
    """便捷接口：把指定积分值注入到 WorkBuddy

    将 credits 作为叠加值（add_left 和 add_total），注入后 WorkBuddy 显示值 = 真实值 + credits。

    Args:
        credits: 积分余额

    Returns:
        bool: 是否注入成功
    """
    if credits < 0:
        credits = 0
    # 保留小数，去掉末尾的 .0
    if credits == int(credits):
        add_val = str(int(credits))
    else:
        add_val = str(credits)
    return inject(add_left=add_val, add_total=add_val)


def main():
    global ADD_LEFT, ADD_TOTAL, NEW_EDITION, NEW_ISPRO
    watch = '--watch' in sys.argv
    for i, a in enumerate(sys.argv):
        if a=='--value' and i+1<len(sys.argv): ADD_LEFT=sys.argv[i+1]; ADD_TOTAL=sys.argv[i+1]
        elif a=='--edition' and i+1<len(sys.argv): NEW_EDITION=sys.argv[i+1]; NEW_ISPRO=(NEW_EDITION=='pro')

    print("=" * 50)
    print("WorkBuddy 积分叠加  +" + ADD_LEFT + " edition=" + NEW_EDITION)
    print("  (真实积分 + " + ADD_LEFT + " = 显示值)")
    print("=" * 50)

    if not inject():
        sys.exit(1)

    print("\n[DONE] 注入完成")
    print("[TIP] 可随时改 --value 重跑，无需重启 WorkBuddy")
    if watch:
        print("[WATCH] 每 " + str(WATCH_INTERVAL) + "s 重新注入，Ctrl+C 退出")
        try:
            while True:
                time.sleep(WATCH_INTERVAL)
                print("\n[" + time.strftime("%H:%M:%S") + "] 重新注入...")
                try: inject()
                except Exception as e: print("[WARN] " + str(e))
        except KeyboardInterrupt:
            print("\n[EXIT]")


if __name__ == '__main__':
    main()
