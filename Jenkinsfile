pipeline {
    agent any

    environment {
        COMPOSE_PROJECT_NAME = "autoquiz"
    }

    stages {
        stage('Clone Repository') {
            steps {
                git branch: 'main', url: 'https://github.com/ABHISAM2289/Auto-quiz.git'

            }
        }

        stage('Stop Existing Containers') {
            steps {
                dir('Auto-quiz') {
                    sh 'docker-compose down || true'
                }
            }
        }

        stage('Build and Deploy') {
            steps {
                
                    sh '''
                        docker-compose build
                        docker-compose up -d
                    '''
                
            }
        }
    }

    post {
        failure {
            echo 'Build failed!'
        }
        success {
            echo 'Build and deployment successful!'
        }
    }
}
