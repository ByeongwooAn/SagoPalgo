abstract interface class OrderSimulationRepository {
  Future<List<Map<String, dynamic>>> simulationSessions();
  Future<Map<String, dynamic>> createSimulation(num cash);
  Future<Map<String, dynamic>> simulation(String id);
  Future<Map<String, dynamic>> simulationAction(
    String id,
    String path,
    Map<String, dynamic> body,
  );
}
