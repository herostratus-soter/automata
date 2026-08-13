class TokenTracker:
    """Clase encargada de acumular y reportar el consumo de tokens de Gemini."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.mostrar_reporte = True  # Controla si se imprime el resumen en consola

    def sumar(self, usage_metadata):
        """Acumula los tokens devueltos por la respuesta de Gemini."""
        if usage_metadata:
            self.input_tokens += getattr(usage_metadata, 'prompt_token_count', 0)
            self.output_tokens += getattr(usage_metadata, 'candidates_token_count', 0)

    def reporte_final(self):
        """Muestra en consola el resumen detallado de consumo y costos si está habilitado."""
        if not self.mostrar_reporte:
            return  # Si en config.py está en False, no imprime nada

        total = self.input_tokens + self.output_tokens
        # Precios base aproximados de Gemini 2.5 Flash
        costo_input = (self.input_tokens / 1_000_000) * 0.075
        costo_output = (self.output_tokens / 1_000_000) * 0.30
        costo_total = costo_input + costo_output

        print("\n" + "=" * 55)
        print("          RESUMEN DE CONSUMO DE TOKENS (GEMINI)")
        print("=" * 55)
        print(f" Tokens de Entrada (Input Prompt):   {self.input_tokens:>10,}")
        print(f" Tokens de Salida  (Output Text):    {self.output_tokens:>10,}")
        print("-" * 55)
        print(f" TOTAL TOKENS CONSUMIDOS:            {total:>10,}")
        print(f" Costo aproximado estimado:          ${costo_total:>10.6f} USD")
        print("=" * 55 + "\n")


# Instancia global por defecto para usarse fácilmente en cualquier script
tracker = TokenTracker()
