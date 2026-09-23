import os
import io
import json
import tarfile
import shutil
import tempfile
import subprocess
import requests
import pandas as pd
import numpy as np

from pathlib import Path

# ============================================================
# CONFIGURAÇÕES
# ============================================================

CSV_PATH = "/home/jamisil/experimento_cc_java/ck/dataset_java_ai_balanceado.csv"

CK_JAR = (
    "/home/jamisil/experimento_cc_java/ck/"
    "target/ck-0.7.1-SNAPSHOT-jar-with-dependencies.jar"
)

RESULTS_DIR = Path(
    "/home/jamisil/experimento_cc_java/ck/results/ck_metrics"
)

# Caminho para o ficheiro de histórico com os PRs já processados
HISTORICO_PATH = "/home/jamisil/experimento_cc_java/ck/lote1_concluidos.txt"

# Quantos PRs processar por execução antes de parar
TAMANHO_LOTE = 150  

GITHUB_API = "https://api.github.com"
TEST_ONLY = None
SKIP_COMPLETED = True
DOWNLOAD_TIMEOUT = 300

# ============================================================
# TOKEN DO GITHUB
# ============================================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ck-pr-metrics-experiment"
}

if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    print("GitHub Token: configurado")
else:
    print("GitHub Token: NÃO configurado")

# ============================================================
# CARREGAR HISTÓRICO DE PRs CONCLUÍDOS
# ============================================================

prs_historico = set()

if SKIP_COMPLETED and os.path.exists(HISTORICO_PATH):
    with open(HISTORICO_PATH, "r", encoding="utf-8") as f:
        prs_historico = set(linha.strip() for linha in f if linha.strip())
    print(f"📚 Histórico carregado: {len(prs_historico)} PRs previamente concluídos serão ignorados.")
else:
    print("📚 Nenhum ficheiro de histórico encontrado.")

def registrar_historico(nome_experimento):
    with open(HISTORICO_PATH, "a", encoding="utf-8") as f:
        f.write(f"{nome_experimento}\n")
    prs_historico.add(nome_experimento)


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def limpar_nome(nome):
    nome = str(nome)
    caracteres = ["/", "\\", ":", "*", "?", "\"", "<", ">", "|", " "]
    for c in caracteres:
        nome = nome.replace(c, "_")
    return nome

def requests_get(url, params=None):
    response = requests.get(url, headers=HEADERS, params=params, timeout=60)
    if response.status_code == 403:
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        raise RuntimeError(f"GitHub API 403. Limite restante: {remaining}, reset: {reset}")
    response.raise_for_status()
    return response

def obter_dados_pr(pr_url):
    pr_url = pr_url.rstrip("/")
    partes = pr_url.split("/")
    owner, repo, pr_number = partes[3], partes[4], int(partes[6])
    api_url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
    
    response = requests_get(api_url)
    data = response.json()
    base, head = data.get("base", {}), data.get("head", {})

    resultado = {
        "pr_url": pr_url, "owner": owner, "repo": repo, "pr_number": pr_number,
        "base_sha": base.get("sha"), "base_ref": base.get("ref"),
        "head_sha": head.get("sha"), "head_ref": head.get("ref"),
        "merged": data.get("merged", False), "merge_commit_sha": data.get("merge_commit_sha"),
    }
    return resultado

def baixar_snapshot(owner, repo, sha, destino):
    url = f"https://github.com/{owner}/{repo}/archive/{sha}.tar.gz"
    response = requests.get(url, headers=HEADERS, timeout=DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo_tar = destino / "snapshot.tar.gz"
    with open(arquivo_tar, "wb") as f:
        f.write(response.content)
    return arquivo_tar

def extrair_snapshot(arquivo_tar, destino):
    destino = Path(destino)
    with tarfile.open(arquivo_tar, "r:gz") as tar:
        tar.extractall(destino)
    diretorios = [p for p in destino.iterdir() if p.is_dir()]
    return diretorios[0]

def contar_arquivos_java(source_dir):
    return len(list(Path(source_dir).rglob("*.java")))

def executar_ck(source_dir, output_dir):
    source_dir, output_dir = Path(source_dir).resolve(), Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comando = ["java", "-jar", str(Path(CK_JAR).resolve()), str(source_dir), "false", "0", str(output_dir)]
    
    resultado = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(output_dir))
    if resultado.returncode != 0:
        raise RuntimeError(f"CK terminou com erro. Exit code: {resultado.returncode}")
    return output_dir

def encontrar_csvs(ck_dir):
    return list(Path(ck_dir).rglob("*.csv"))

def preparar_chave_entidade(df, tipo_csv):
    df = df.copy()
    colunas = set(df.columns)
    if tipo_csv == "class":
        df["_entity_key"] = df["file"].fillna("").astype(str) + "::" + df["class"].fillna("").astype(str) if "file" in colunas and "class" in colunas else df["class"].fillna("").astype(str)
    elif tipo_csv == "method":
        partes = [df[col].fillna("").astype(str) for col in ["file", "class", "method"] if col in colunas]
        chave = "::".join(partes)
        for col in ["signature", "parameters", "parameterTypes", "parameter_types", "paramTypes", "params"]:
            if col in colunas:
                chave += "::" + df[col].fillna("").astype(str)
                break
        df["_entity_key"] = chave
    return df

def identificar_tipo_csv(nome):
    return "class" if nome.lower() == "class.csv" else "method" if nome.lower() == "method.csv" else None

def carregar_csv(path):
    try:
        return pd.read_csv(path, low_memory=False)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1", low_memory=False)

def valor_eh_bool(serie):
    if pd.api.types.is_bool_dtype(serie): return True
    valores = set(serie.dropna().astype(str).str.lower().unique())
    return len(valores) > 0 and valores.issubset({"true", "false"})

def tentar_converter_numero(serie):
    if valor_eh_bool(serie): return None
    convertida = pd.to_numeric(serie, errors="coerce")
    return convertida if serie.notna().sum() > 0 and (convertida.notna().sum() / serie.notna().sum()) >= 0.95 else None

def comparar_csv(before_path, after_path, output_path):
    tipo = identificar_tipo_csv(Path(before_path).name)
    if tipo is None: return None
    
    before, after = carregar_csv(before_path), carregar_csv(after_path)
    before, after = preparar_chave_entidade(before, tipo), preparar_chave_entidade(after, tipo)
    
    before = before.drop_duplicates(subset="_entity_key").set_index("_entity_key")
    after = after.drop_duplicates(subset="_entity_key").set_index("_entity_key")
    
    comuns = set(before.index) & set(after.index)
    adicionadas, removidas = set(after.index) - set(before.index), set(before.index) - set(after.index)
    colunas_comuns = set(before.columns) & set(after.columns) - {"_entity_key"}
    
    metricas_numericas = [col for col in colunas_comuns if tentar_converter_numero(before[col]) is not None and tentar_converter_numero(after[col]) is not None]
    
    resultados = []
    for entity in comuns:
        for metric in metricas_numericas:
            v_b, v_a = float(before.loc[entity, metric]), float(after.loc[entity, metric])
            if pd.isna(v_b) or pd.isna(v_a):
                resultados.append({"entity": entity, "metric": metric, "before": np.nan, "after": np.nan, "delta": np.nan, "status": "UNKNOWN", "value_type": "numeric"})
            else:
                delta = v_a - v_b
                status = "INCREASED" if delta > 0 else "DECREASED" if delta < 0 else "UNCHANGED"
                resultados.append({"entity": entity, "metric": metric, "before": v_b, "after": v_a, "delta": delta, "status": status, "value_type": "numeric"})
                
    for entity in adicionadas:
        for metric in metricas_numericas:
            resultados.append({"entity": entity, "metric": metric, "before": np.nan, "after": after.loc[entity, metric], "delta": np.nan, "status": "ADDED", "value_type": "numeric"})
            
    for entity in removidas:
        for metric in metricas_numericas:
            resultados.append({"entity": entity, "metric": metric, "before": before.loc[entity, metric], "after": np.nan, "delta": np.nan, "status": "REMOVED", "value_type": "numeric"})
            
    df_res = pd.DataFrame(resultados)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df_res.to_csv(output_path, index=False)
    return df_res

def gerar_deltas(before_dir, after_dir, delta_dir):
    delta_dir = Path(delta_dir)
    delta_dir.mkdir(parents=True, exist_ok=True)
    before_csvs, after_csvs = {p.name: p for p in Path(before_dir).rglob("*.csv")}, {p.name: p for p in Path(after_dir).rglob("*.csv")}
    for nome in set(before_csvs) & set(after_csvs):
        try: comparar_csv(before_csvs[nome], after_csvs[nome], delta_dir / nome)
        except Exception: pass

def gerar_delta_summary(delta_dir, output_path):
    arquivos = [p for p in Path(delta_dir).glob("*.csv") if p.name != "delta_summary.csv"]
    todos = []
    for arquivo in arquivos:
        try:
            df = pd.read_csv(arquivo, low_memory=False)
            if not df.empty:
                df["source_csv"] = arquivo.name
                todos.append(df)
        except: pass
    if not todos: return None
    df = pd.concat(todos, ignore_index=True)
    df = df[df["value_type"] == "numeric"].copy()
    
    resumo = df.groupby(["source_csv", "metric"], dropna=False).agg(before_mean=("before", "mean"), after_mean=("after", "mean"), delta_mean=("delta", "mean")).reset_index()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(output_path, index=False)
    return resumo

def pr_ja_processado(pr_dir):
    return (pr_dir / "before").exists() and (pr_dir / "delta").exists()

# ============================================================
# PROCESSAR UM PR
# ============================================================

def processar_pr(row):
    pr_url, pr_id = row["html_url"], str(row.get("id", "unknown"))
    autoria = limpar_nome(row.get("Autoria", "unknown"))
    nome_experimento = f"{autoria}_{pr_id}"
    pr_dir = RESULTS_DIR / nome_experimento

    print(f"\n# PROCESSANDO PR: {pr_id} ({autoria})")
    
    if SKIP_COMPLETED:
        if nome_experimento in prs_historico:
            print("⏭️ PR já consta no ficheiro de histórico txt. Pulando...")
            return {"status": "SKIPPED_TXT", "pr_url": pr_url, "id": pr_id}
        if pr_ja_processado(pr_dir):
            print("⏭️ PR já processado localmente. Pulando...")
            registrar_historico(nome_experimento) 
            return {"status": "SKIPPED_LOCAL", "pr_url": pr_url, "id": pr_id}

    pr_dir.mkdir(parents=True, exist_ok=True)
    before_dir, after_dir, delta_dir = pr_dir / "before", pr_dir / "after", pr_dir / "delta"

    try:
        dados = obter_dados_pr(pr_url)
        with open(pr_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump({**dados, "dataset_id": pr_id, "autoria": row.get("Autoria")}, f, indent=2)

        temp_root = Path(tempfile.mkdtemp(prefix="ck_pr_"))
        
        # Before
        before_download = temp_root / "before_download"
        arquivo_before = baixar_snapshot(dados["owner"], dados["repo"], dados["base_sha"], before_download)
        executar_ck(extrair_snapshot(arquivo_before, temp_root / "before_extract"), before_dir)
        
        # After
        after_download = temp_root / "after_download"
        arquivo_after = baixar_snapshot(dados["owner"], dados["repo"], dados["head_sha"], after_download)
        executar_ck(extrair_snapshot(arquivo_after, temp_root / "after_extract"), after_dir)

        # Deltas
        gerar_deltas(before_dir, after_dir, delta_dir)
        gerar_delta_summary(delta_dir, pr_dir / "delta_summary.csv")

        print("✓ PR CONCLUÍDO COM SUCESSO")
        registrar_historico(nome_experimento)

        return {"status": "SUCCESS", "pr_url": pr_url, "id": pr_id}

    except Exception as e:
        print(f"❌ ERRO NO PR: {e}")
        with open(pr_dir / "error.txt", "w", encoding="utf-8") as f: f.write(str(e))
        registrar_historico(nome_experimento)
        
        return {"status": "ERROR", "pr_url": pr_url, "id": pr_id, "error": str(e)}

    finally:
        try: shutil.rmtree(temp_root, ignore_errors=True)
        except Exception: pass

# ============================================================
# CARREGAR DATASET
# ============================================================

df = pd.read_csv(CSV_PATH, low_memory=False)
df_java = df[df["language"].astype(str).str.lower().eq("java")].copy()

# ============================================================
# LOOP PRINCIPAL
# ============================================================

resultados = []
prs_processados_neste_lote = 0 

for indice, (_, row) in enumerate(df_java.iterrows(), start=1):
    
    resultado = processar_pr(row)
    resultados.append(resultado)
    
    if resultado["status"] in ["SUCCESS", "ERROR"]:
        prs_processados_neste_lote += 1
        print(f"📈 Progresso do Lote: {prs_processados_neste_lote}/{TAMANHO_LOTE}")
        
    if prs_processados_neste_lote >= TAMANHO_LOTE:
        break

if prs_processados_neste_lote > 0:
    print("\n" + "=" * 80)
    print(f"📦 LOTE DE {TAMANHO_LOTE} PRs CONCLUÍDO COM SUCESSO")
    print("=" * 80)
    print(f"Os resultados estão prontos na pasta:\n{RESULTS_DIR}")
    print("\n⚠️ ATENÇÃO: Faça o upload manual para o Google Drive e limpe o conteúdo")
    print("desta pasta (results/ck_metrics) antes de executar o script novamente!")
else:
    print("\nNenhum PR novo processado neste ciclo.")
