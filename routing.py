import requests

def buscar_rota(origem, destino):
    lat_origem, lat_destino = (origem["lat"], destino["lat"])
    lng_origem, lng_destino = (origem["lng"], destino["lng"])
    url = f"https://routing.openstreetmap.de/routed-foot/route/v1/driving/{lng_origem},{lat_origem};{lng_destino},{lat_destino}"

    try:
        resposta = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": "Projeto3ProgEficaz/1.0"},
            timeout=10
        )
        resposta.raise_for_status()

        dados = resposta.json()

        if dados.get("code") != "Ok" or not dados.get("routes"):
            return None

        rota = dados["routes"][0]
        pontos = rota["geometry"]["coordinates"]
        pontos_invertidos = []
        for ponto in pontos:
            pontos_invertidos.append([ponto[1], ponto[0]])

        return {
            "duracao_min": rota["duration"]/60,
            "distancia_km": round(rota["distance"]/1000, 2),
            "coordenadas": pontos_invertidos
        }
    except requests.exceptions.RequestException:
        return None
