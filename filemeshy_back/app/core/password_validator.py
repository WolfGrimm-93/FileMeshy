from typing import List
from app.core.security import verify_password


class PasswordValidator:
    """Validador de contraseñas con historial."""
    
    @staticmethod
    def check_password_reuse(
        new_password: str,
        current_hash: str,
        password_history: List[str] = None
    ) -> tuple[bool, str]:
        """
        Verifica que la contraseña no haya sido usada recientemente.
        
        Args:
            new_password: Nueva contraseña en texto plano
            current_hash: Hash de la contraseña actual
            password_history: Lista de hashes de contraseñas anteriores
            
        Returns:
            (es_valida, mensaje_error)
        """
        password_history = password_history or []
        
        # Verificar contra contraseña actual
        if verify_password(new_password, current_hash):
            return False, "No puedes usar tu contraseña actual. Elige una contraseña diferente"
        
        # Verificar contra historial (últimas 5 contraseñas)
        for old_hash in password_history[:5]:
            if verify_password(new_password, old_hash):
                return False, "Esta contraseña ya fue utilizada anteriormente. Por seguridad, elige una contraseña diferente"
        
        return True, ""
    
    @staticmethod
    def add_to_history(
        current_hash: str,
        password_history: List[str] = None,
        max_history: int = 5
    ) -> List[str]:
        """
        Agrega la contraseña actual al historial.
        
        Args:
            current_hash: Hash de la contraseña actual a guardar
            password_history: Lista actual de hashes históricos
            max_history: Cantidad máxima de contraseñas a recordar (default: 5)
            
        Returns:
            Nueva lista de historial actualizada
        """
        password_history = password_history or []
        
        # Agregar la contraseña actual al inicio
        new_history = [current_hash] + password_history
        
        # Mantener solo las últimas N contraseñas
        return new_history[:max_history]


password_validator = PasswordValidator()
