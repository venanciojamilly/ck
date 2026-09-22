import os
import itertools
import pandas as pd
from scipy import stats

def analisar_todas_as_autorias(results_path="/home/jamisil/experimento_cc_java/ck/results/ck_metrics", csv_path="/home/jamisil/experimento_cc_java/ck/dataset_java_ai_balanceado.csv"):
    df_dataset = pd.read_csv(csv_path)
    df_dataset['qid'] = df_dataset['Autoria'].astype(str) + "_" + df_dataset['id'].astype(str)
    
    registros_classes = []
    if not os.path.exists(results_path):
        print(f"⚠️ O diretório {results_path} não foi encontrado.")
        return
        
    for pasta in os.listdir(results_path):
        caminho_class_csv = os.path.join(results_path, pasta, "class.csv")
        
        # Verifica se o arquivo existe e não está vazio
        if os.path.exists(caminho_class_csv) and os.path.getsize(caminho_class_csv) > 0:
            try:
                df_class = pd.read_csv(caminho_class_csv)
                # Se o arquivo estiver vazio de colunas, o pandas avisa ou gera erro
                if df_class.empty:
                    continue
                df_class['qid'] = pasta
                registros_classes.append(df_class)
            except Exception:
                # Ignora silenciosamente arquivos corrompidos ou vazios
                pass
                
    if not registros_classes:
        print("⚠️ Nenhum arquivo class.csv válido foi encontrado.")
        return
        
    df_all_classes = pd.concat(registros_classes, ignore_index=True)
    df_completo = pd.merge(df_all_classes, df_dataset[['qid', 'Autoria', 'language']], on='qid', how='inner')
    
    autorias = df_completo['Autoria'].unique()
    print(f"🤖 Autorias disponíveis para cruzamento: {list(autorias)}\n")
    
    metricas_alvo = ['tcc', 'lcom*', 'wmc', 'loc', 'cbo']
    
    for grupo_a, grupo_b in itertools.combinations(autorias, 2):
        print(f"==================================================")
        print(f"ESTATÍSTICA COMPARATIVA: {grupo_a} vs {grupo_b}")
        print(f"==================================================")
        
        df_par = df_completo[df_completo['Autoria'].isin([grupo_a, grupo_b])]
        
        for metrica in metricas_alvo:
            if metrica not in df_par.columns:
                continue
                
            # Força a conversão para numérico, transformando sujeira/erros em NaN e limpando
            valores_a = pd.to_numeric(df_par[df_par['Autoria'] == grupo_a][metrica], errors='coerce').dropna()
            valores_b = pd.to_numeric(df_par[df_par['Autoria'] == grupo_b][metrica], errors='coerce').dropna()
            
            if len(valores_a) == 0 or len(valores_b) == 0:
                continue
                
            med_a, med_b = valores_a.median(), valores_b.median()
            
            try:
                stat, p_value = stats.mannwhitneyu(valores_a, valores_b, alternative='two-sided')
            except Exception:
                continue
            
            print(f"\nMétrica: {metrica.upper()}")
            print(f"  - Mediana ({grupo_a}): {med_a:.4f}")
            print(f"  - Mediana ({grupo_b}): {med_b:.4f}")
            print(f"  - Estatística U: {stat:.2f} | p-value: {p_value:.5f}")
            
            if p_value < 0.05:
                print(f"  -> Diferença ESTATISTICAMENTE SIGNIFICATIVA (p < 0.05)")
            else:
                print(f"  -> Sem diferença estatisticamente significativa (p >= 0.05)")
        print("\n")

if __name__ == "__main__":
    analisar_todas_as_autorias()