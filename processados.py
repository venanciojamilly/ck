import os

def contar_prs_processados(results_path="/home/jamisil/experimento_cc_java/ck/results/ck_metrics"):
    if not os.path.exists(results_path):
        print(f"⚠️ O diretório {results_path} não foi encontrado.")
        return 0
    
    processados_sucesso = 0
    incompletos = 0
    pastas = os.listdir(results_path)
    
    for pasta in pastas:
        caminho_pasta = os.path.join(results_path, pasta)
        
        if os.path.isdir(caminho_pasta):
            # O PR só é um sucesso se concluiu a última etapa: o cálculo do Delta
            caminho_delta = os.path.join(caminho_pasta, "delta", "class.csv")
            
            # (Opcional) Pode também verificar o "before", mas o "delta" garante que tudo rodou
            if os.path.exists(caminho_delta):
                processados_sucesso += 1
            else:
                # Conta pastas que foram criadas, mas falharam a meio (ex: erro 404)
                incompletos += 1
                
    print("==================================================")
    print(f"📊 PRs EFETIVAMENTE PROCESSADOS (100% sucesso): {processados_sucesso}")
    if incompletos > 0:
        print(f"⚠️ PRs ignorados ou incompletos (ex: erro 404): {incompletos}")
    print("==================================================")
    
    return processados_sucesso

if __name__ == "__main__":
    contar_prs_processados()