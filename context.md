<?xml version="1.0" encoding="UTF-8"?>
<Project name="ResQ-Capital">
    <Metadata>
        <Tagline>The "Arbitrage" Platform for Humanitarian Aid Allocation.</Tagline>
        <Objective>Identify underfunded global crises using Databricks and validate logistical/safety feasibility using computer vision and vector RAG.</Objective>
    </Metadata>

    <Architecture>
        <DesignPattern>Modular Service Pattern</DesignPattern>
        <Philosophy>Isolation of concerns. Each module (pipeline, vision, vector, synthesis) should be functional and testable independently.</Philosophy>
        <Orchestration>app.py (Streamlit) acts as the central hub, importing logic from the modules/ directory.</Orchestration>
        <DataFlow>
            <Step order="1" source="Databricks (pipeline.py)" destination="data/neglect_scores.json">Ingest and calculate neglect scores.</Step>
            <Step order="2" source="modules/vision.py &amp; modules/vector.py" trigger="Coordinate Consumption">Validate logistical and safety context.</Step>
            <Step order="3" source="synthesis.py (Sphinx)" trigger="Combination">Generate deployment plan memo.</Step>
        </DataFlow>
    </Architecture>

    <TechStack>
        <Track sponsor="Databricks" challenge="Geo-Insight">
            <Component>Core Engine (PySpark/Python)</Component>
        </Track>
        <Track sponsor="GrowthFactor" challenge="Parking Detection">
            <Component>Logistics (CV/Satellite)</Component>
        </Track>
        <Track sponsor="Actian" challenge="VectorAI">
            <Component>Safety RAG (VectorAI)</Component>
        </Track>
        <Track sponsor="Sphinx" challenge="Unique Application">
            <Component>Intelligence (LLM)</Component>
        </Track>
        <Track sponsor="SafetyKit" challenge="Human Safety">
            <Component>Safety Layer</Component>
        </Track>
    </TechStack>

    <RepositoryStructure>
        <Folder name="resq-capital">
            <Folder name="data">
                <Description>Shared JSON/CSV outputs</Description>
            </Folder>
            <Folder name="modules">
                <File name="pipeline.py">P1: ACAPS/FTS Data Engineering</File>
                <File name="vision.py">P2: Satellite CV logic</File>
                <File name="vector.py">P2: Actian RAG logic</File>
                <File name="synthesis.py">P3: Sphinx Prompting</File>
            </Folder>
            <File name="app.py">Main Dashboard (Streamlit)</File>
            <File name=".env">Secrets and API Keys</File>
            <File name="requirements.txt">Shared dependencies</File>
        </Folder>
    </RepositoryStructure>

    <TeamRoles>
        <Role id="P1" title="Data Engineer">
            <AssignedTo>Person 1</AssignedTo>
            <OutputTarget>data/neglect_scores.json</OutputTarget>
            <DataContract format="JSON">
                <![CDATA[
                {
                  "crisis_id": "str",
                  "country": "str",
                  "coordinates": {"lat": 0.0, "lng": 0.0},
                  "neglect_score": 0.0,
                  "severity": 0,
                  "funding_gap_usd": 0
                }
                ]]>
            </DataContract>
        </Role>
        <Role id="P2" title="AI Specialist">
            <AssignedTo>Person 2</AssignedTo>
            <Functions>
                <Function name="get_parking_capacity">Returns integer count based on lat/lng.</Function>
                <Function name="get_safety_report">Returns text summary via Actian.</Function>
            </Functions>
        </Role>
        <Role id="P3" title="Product Architect">
            <AssignedTo>Person 3</AssignedTo>
            <Functions>
                <Function name="generate_memo">Calls Sphinx with aggregated data.</Function>
                <Function name="ui_logic">Map visualization via Folium/Streamlit.</Function>
            </Functions>
        </Role>
    </TeamRoles>

    <StrategicGuardrails>
        <Guardrail id="1">Zero-Inference: Do not assume safety on missing data.</Guardrail>
        <Guardrail id="2">Modular Imports: app.py must only import from modules/.</Guardrail>
        <Guardrail id="3">Mocking: Use mock functions for frontend stability if APIs are unstable.</Guardrail>
        <Guardrail id="4">SafetyKit Integration: Flag 'Logistics Red Alert' if neglect is high but parking is zero.</Guardrail>
    </StrategicGuardrails>
</Project>