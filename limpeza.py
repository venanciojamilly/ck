import os

def remover_pastas_vazias_recursivo(diretorio_base):
    if not os.path.exists(diretorio_base):
        print(f"⚠️ O diretório {diretorio_base} não existe.")
        return

    pastas_removidas = 0

    print("🔍 A iniciar varredura em busca de pastas vazias...")
    
    # os.walk com topdown=False garante que olhamos para as subpastas (ex: /before) 
    # ANTES de olharmos para a pasta principal do PR.
    for root, dirs, files in os.walk(diretorio_base, topdown=False):
        for dir_name in dirs:
            caminho_pasta = os.path.join(root, dir_name)
            
            # os.listdir verifica o que há dentro da pasta. Se for uma lista vazia [], está vazia.
            if not os.listdir(caminho_pasta):
                try:
                    os.rmdir(caminho_pasta) # Comando seguro: o SO bloqueia se tiver algum arquivo
                    
                    # Formata o print para ficar mais legível no terminal
                    caminho_curto = caminho_pasta.replace(diretorio_base, "")
                    print(f"🗑️ Pasta vazia removida: {caminho_curto}")
                    
                    pastas_removidas += 1
                except Exception as e:
                    print(f"⚠️ Erro ao remover {caminho_curto}: {e}")

    print("==================================================")
    print(f"🧹 Limpeza concluída! Total de pastas vazias apagadas: {pastas_removidas}")
    print("==================================================")

if __name__ == "__main__":
    # O caminho exato onde as suas métricas estão a ser guardadas
    caminho_alvo = "/home/jamisil/experimento_cc_java/ck/results/ck_metrics"
    remover_pastas_vazias_recursivo(caminho_alvo)