def guarda_asse_singolo_punto(fig, n_valori_unici: int) -> None:
    """Evita i tick temporali degenerati che Plotly genera sull'asse x quando c'è
    un solo valore univoco (es. '23:59:59.999' invece di una singola data
    leggibile) - capita sia con colonne datetime sia con stringhe che Plotly
    interpreta come temporali (es. "2026-07"). Forzare l'asse a categoria con un
    solo punto non cambia nulla visivamente (non c'è nulla da posizionare in
    proporzione) ma elimina l'autoscaling temporale degenere.
    """
    if n_valori_unici <= 1:
        fig.update_xaxes(type="category")
