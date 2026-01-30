class DataPacket:
    """Simple container for data flowing through the pipeline"""
    def __init__(self):
        self.input = {}
        self.data = {}
        self.parameters = {}
        self.metadata = {}
        self.output = None
    
    def __str__(self):
        return f"DataPacket(input={self.input}, data_keys={list(self.data.keys())}, output={self.output})"