#!/usr/bin/env python3
"""Cliente de fumaca: conecta no endpoint MCP e exercita as ferramentas."""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

URL = os.environ.get("GEODB_URL", "http://127.0.0.1:9000/mcp")
TOKEN = os.environ.get("GEODB_TOKEN", "")

CASOS = [
    ("geoquimica_formacao", {"nome": "Formação Ipubi"}),
    ("buscar_poco", {"nome": "2-AP-1-CE"}),
    ("listar_formacoes", {"grupo": "Santana"}),
    ("controversias", {"tema": "ingressão marinha"}),
    ("busca_livre", {"termo": "calcário laminado"}),
    ("descrever_bacia", {"nome": "Araripe"}),
]


async def main() -> int:
    headers = {"X-API-Key": TOKEN} if TOKEN else {}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(URL, http_client=http) as streams:
            ler, escrever = streams[0], streams[1]
            async with ClientSession(ler, escrever) as s:
                await s.initialize()
                ferramentas = await s.list_tools()
                nomes = [t.name for t in ferramentas.tools]
                print(f"ferramentas expostas ({len(nomes)}): {', '.join(nomes)}\n")

                for nome, args in CASOS:
                    r = await s.call_tool(nome, args)
                    texto = "".join(c.text for c in r.content if hasattr(c, "text"))
                    resumo = texto if len(texto) < 300 else texto[:297] + "..."
                    print(f"── {nome}({json.dumps(args, ensure_ascii=False)})\n{resumo}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
