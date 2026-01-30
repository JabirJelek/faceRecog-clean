import time
from ..core.context import DataPacket
import time

class PipelineOrchestrator:
    """Manages the execution of processors in sequence"""
    def __init__(self, name="pipeline", config=None):
        self.name = name
        self.config = config or {}
        self.processors = {}
        self.execution_order = []
    
    def add_processor(self, name, processor):
        """Add a processor to the pipeline"""
        self.processors[name] = processor
        return self
    
    def set_execution_order(self, order):
        """Set the order in which processors should execute"""
        self.execution_order = order
        return self
    
    def execute(self, input_data, parameters=None):
        """Execute the pipeline with given input data and parameters"""
        print(f"\n=== Executing Pipeline: {self.name} ===")
        
        # Create data packet
        packet = DataPacket()
        packet.input = input_data
        packet.parameters = parameters or {}
        
        # Use perf_counter for more accurate timing
        start_time = time.perf_counter()
        
        # Execute each processor in order
        for processor_name in self.execution_order:
            if processor_name not in self.processors:
                print(f"Warning: Processor '{processor_name}' not found, skipping")
                continue
            
            processor = self.processors[processor_name]
            
            # Configure processor with parameters
            processor.configure(packet.parameters)
            
            # Process the packet
            try:
                print(f"→ Executing: {processor_name}")
                processor.process(packet)
            except Exception as e:
                print(f"Error in processor {processor_name}: {e}")
                packet.metadata[f"{processor_name}_error"] = str(e)
        
        # Calculate processing time with a minimum threshold
        end_time = time.perf_counter()
        processing_time_seconds = end_time - start_time
        
        # Ensure we never have zero time (minimum 1 microsecond)
        if processing_time_seconds < 0.000001:  # Less than 1 microsecond
            processing_time_seconds = 0.000001
        
        packet.metadata['total_processing_time_seconds'] = processing_time_seconds
        packet.metadata['total_processing_time_ms'] = processing_time_seconds * 1000
        
        print(f"✓ Pipeline completed in {packet.metadata['total_processing_time_ms']:.6f} ms")
        
        return packet    
    