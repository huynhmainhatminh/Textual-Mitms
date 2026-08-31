import asyncio
import threading
import json
import re
from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy import http, tcp
