"""
Atlas Flight CLI Error Taxonomy
Classifies and handles different types of errors from atlas-flight commands
"""

from typing import Optional
import time


class AtlasError(Exception):
    """Base error for Atlas CLI operations"""
    
    def __init__(
        self,
        message: str,
        stderr: Optional[str] = None,
        retryable: bool = False,
        code: Optional[str] = None,
        request_id: Optional[str] = None
    ):
        super().__init__(message)
        self.stderr = stderr
        self.retryable = retryable
        self.code = code
        self.request_id = request_id


class AuthError(AtlasError):
    """Authentication-related errors"""
    pass


class SearchError(AtlasError):
    """Search-related errors"""
    pass


class OfferError(AtlasError):
    """Offer-related errors"""
    pass


class OfferExpiredError(OfferError):
    """Offer has expired and is no longer available"""
    pass


class OfferUnavailableError(OfferError):
    """Offer is no longer available (e.g., seats sold out)"""
    pass


class BookingError(AtlasError):
    """Booking-related errors"""
    pass


class PriceChangedError(BookingError):
    """Price has changed since offer was created"""
    
    def __init__(
        self,
        message: str,
        original_price: float,
        new_price: float,
        currency: str,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.original_price = original_price
        self.new_price = new_price
        self.currency = currency
        self.price_diff = new_price - original_price


class SeatUnavailableError(BookingError):
    """Preferred seat is not available"""
    pass


class OrderError(AtlasError):
    """Order-related errors"""
    pass


class PaymentError(OrderError):
    """Payment-related errors"""
    pass


class PaymentIndeterminateError(PaymentError):
    """Payment outcome is uncertain - do not retry"""
    
    def __init__(self, message: str, order_id: str, **kwargs):
        super().__init__(message, retryable=False, **kwargs)
        self.order_id = order_id


class OrderCreationIndeterminateError(OrderError):
    """Order creation outcome is uncertain - do not retry"""
    
    def __init__(self, message: str, booking_id: str, **kwargs):
        super().__init__(message, retryable=False, **kwargs)
        self.booking_id = booking_id


class ErrorClassifier:
    """Classifies errors from Atlas envelope responses"""
    
    ERROR_CODE_MAP = {
        # Auth errors
        'AUTH_REQUIRED': (AuthError, False),
        'AUTH_EXPIRED': (AuthError, False),
        'AUTH_FAILED': (AuthError, False),
        
        # Search errors
        'SEARCH_FAILED': (SearchError, True),
        'NO_RESULTS': (SearchError, False),
        'INVALID_ROUTE': (SearchError, False),
        
        # Offer errors
        'OFFER_EXPIRED': (OfferExpiredError, False),
        'OFFER_UNAVAILABLE': (OfferUnavailableError, False),
        'OFFER_NOT_FOUND': (OfferError, False),
        
        # Booking errors
        'PRICE_CHANGED': (PriceChangedError, False),
        'SEAT_UNAVAILABLE': (SeatUnavailableError, False),
        'BOOKING_FAILED': (BookingError, True),
        
        # Order errors
        'ORDER_CREATION_INDETERMINATE': (OrderCreationIndeterminateError, False),
        'PAYMENT_FAILED': (PaymentError, True),
        'PAYMENT_INDETERMINATE': (PaymentIndeterminateError, False),
        'INSUFFICIENT_BALANCE': (PaymentError, False),
    }
    
    @classmethod
    def classify(cls, code: str, message: str, retryable: bool, data: dict) -> Optional[AtlasError]:
        """Classify an error code into appropriate error type"""
        
        if code in cls.ERROR_CODE_MAP:
            error_class, default_retryable = cls.ERROR_CODE_MAP[code]
            
            # Special handling for specific error types
            if error_class == PriceChangedError:
                return PriceChangedError(
                    message=message,
                    original_price=data.get('original_price', 0),
                    new_price=data.get('new_price', 0),
                    currency=data.get('currency', 'USD'),
                    retryable=default_retryable,
                    code=code
                )
            elif error_class == PaymentIndeterminateError:
                return PaymentIndeterminateError(
                    message=message,
                    order_id=data.get('order_id', 'unknown'),
                    code=code
                )
            elif error_class == OrderCreationIndeterminateError:
                return OrderCreationIndeterminateError(
                    message=message,
                    booking_id=data.get('booking_id', 'unknown'),
                    code=code
                )
            else:
                return error_class(
                    message=message,
                    retryable=default_retryable,
                    code=code
                )
        
        # Unknown error code - use generic AtlasError
        return AtlasError(
            message=message,
            retryable=retryable,
            code=code
        )


class RetryStrategy:
    """Implements retry logic with exponential backoff"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def should_retry(self, error: AtlasError, attempt: int) -> bool:
        """Determine if we should retry based on error and attempt number"""
        if attempt >= self.max_retries:
            return False
        
        if not error.retryable:
            return False
        
        # Never retry indeterminate errors
        if isinstance(error, (PaymentIndeterminateError, OrderCreationIndeterminateError)):
            return False
        
        return True
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay before next retry"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay)
    
    def execute_with_retry(self, func, *args, **kwargs):
        """Execute function with retry logic"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except AtlasError as e:
                last_error = e
                
                if not self.should_retry(e, attempt):
                    raise
                
                delay = self.get_delay(attempt)
                time.sleep(delay)
        
        # Should not reach here, but just in case
        if last_error:
            raise last_error
