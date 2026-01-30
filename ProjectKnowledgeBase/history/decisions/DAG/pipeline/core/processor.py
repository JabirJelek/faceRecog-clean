class Processor:
    """Simple processor class - NOT abstract, can be instantiated directly"""
    def __init__(self, name, config=None):
        self.name = name
        self.config = config or {}
        self.parameters = {}
    
    def configure(self, params):
        """Configure the processor with parameters"""
        self.parameters.update(params)
        return self
    
    def process(self, packet):
        """Process the data packet - to be overridden by subclasses"""
        print(f"[{self.name}] Processing packet")
        return packet
    
    def __str__(self):
        return f"Processor(name='{self.name}')"